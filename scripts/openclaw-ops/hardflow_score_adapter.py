#!/usr/bin/env python3
"""将 HardFlow score-gate-audit.ndjson 转换为 upgrade_analysis.py 可消费的 executor report 格式。

作用：接通 HardFlow 评分数据 → evolution-upgrader 的弱项分析闭环。

输入：score-gate-audit.ndjson（每行一个 JSON，由 check-score-gate.mjs 在每次评分校验后写入）
输出：executor report JSON 文件（可被 upgrade_analysis.py 的 load_reports() 消费）

用法：
    python3 hardflow_score_adapter.py <audit_ndjson_path> [--output <output_json_path>]
    python3 hardflow_score_adapter.py .workflow/runs/20260329_120000/score-gate-audit.ndjson
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

JSONDict = dict[str, Any]


def parse_ndjson(file_path: Path) -> list[JSONDict]:
    """解析 NDJSON 文件，跳过空行和无效行。

    Args:
        file_path: NDJSON 文件路径

    Returns:
        解析后的 JSON 对象列表
    """
    records: list[JSONDict] = []
    for line_nr, raw_line in enumerate(file_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                records.append(obj)
            else:
                print(f"[adapter] line {line_nr}: skipping non-object JSON", file=sys.stderr)
        except json.JSONDecodeError as exc:
            print(f"[adapter] line {line_nr}: JSON parse error: {exc}", file=sys.stderr)
    return records


def audit_record_to_result(record: JSONDict) -> JSONDict:
    """将单条 score-gate-audit 记录转换为 executor result 格式。

    映射关系：
        gate           → assignee (e.g. "reviewer-frontend")
        passed         → status ("passed" / "failed")
        overall_score  → quality_score
        dimensions     → dimension_scores (保留原始结构)
        deduction_reasons → resolution_summary

    Args:
        record: 单条审计记录（来自 score-gate-audit.ndjson）

    Returns:
        executor result 格式的字典
    """
    gate = record.get("gate", "unknown")
    passed = record.get("passed", False)
    overall = record.get("overall_score", record.get("overall", 0))
    dimensions = record.get("dimension_scores", record.get("dimensions", {}))
    deductions = record.get("deduction_reasons", {})
    attempt = record.get("attempt", 1)
    ts = record.get("ts", record.get("timestamp", ""))

    # 构建扣分原因文本摘要
    deduction_parts: list[str] = []
    for dim_name, reasons in deductions.items():
        if isinstance(reasons, list) and reasons:
            dim_score = dimensions.get(dim_name, "?")
            deduction_parts.append(f"{dim_name}({dim_score}): {'; '.join(reasons)}")
    resolution_summary = " | ".join(deduction_parts) if deduction_parts else "no deductions"

    # 构建低分维度列表
    low_dims = [
        {"dimension": k, "score": v}
        for k, v in dimensions.items()
        if isinstance(v, (int, float)) and v < 90
    ]

    return {
        "task_id": f"score-gate-{gate}-attempt-{attempt}",
        "assignee": f"reviewer-{gate}",
        "status": "passed" if passed else "failed",
        "task_status_after": "passed" if passed else "failed",
        "quality_score": overall,
        "gate": gate,
        "attempt": attempt,
        "solved": passed,
        "reason": f"gate={gate} overall={overall} passed={passed}",
        "resolution_summary": resolution_summary,
        "started_at": ts,
        "finished_at": ts,
        "dimension_scores": dimensions,
        "low_dimensions": low_dims,
        "deduction_reasons": deductions,
    }


def build_executor_report(records: list[JSONDict], *, source_path: str) -> JSONDict:
    """将多条审计记录聚合为一个 executor report。

    Args:
        records: 审计记录列表
        source_path: 源文件路径（写入 report 元信息）

    Returns:
        符合 upgrade_analysis.py 输入格式的 executor report
    """
    results = [audit_record_to_result(r) for r in records]

    tasks_selected = len(results)
    tasks_executed = len(results)
    tasks_passed = sum(1 for r in results if r["status"] == "passed")
    tasks_failed = tasks_selected - tasks_passed

    # 时间窗口
    timestamps = [r.get("started_at", "") for r in results if r.get("started_at")]
    window_start = min(timestamps) if timestamps else ""
    window_end = max(timestamps) if timestamps else ""

    # 各 gate 的统计
    gate_summary: dict[str, dict[str, Any]] = {}
    for r in results:
        gate = r["gate"]
        if gate not in gate_summary:
            gate_summary[gate] = {"attempts": 0, "passed": 0, "failed": 0, "avg_score": 0, "scores": []}
        gate_summary[gate]["attempts"] += 1
        gate_summary[gate]["scores"].append(r["quality_score"])
        if r["status"] == "passed":
            gate_summary[gate]["passed"] += 1
        else:
            gate_summary[gate]["failed"] += 1

    for gate_info in gate_summary.values():
        scores = gate_info.pop("scores")
        gate_info["avg_score"] = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "report_type": "hardflow_score_audit",
        "source": source_path,
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "started_at": window_start,
        "finished_at": window_end,
        "tasks_selected": tasks_selected,
        "tasks_executed": tasks_executed,
        "tasks_skipped": 0,
        "tasks_failed": tasks_failed,
        "preflight_warning_tasks": 0,
        "preflight_blocked_tasks": 0,
        "gate_summary": gate_summary,
        "results": results,
    }


def main() -> None:
    """CLI 入口：转换 score-gate-audit.ndjson → executor report JSON。"""
    parser = argparse.ArgumentParser(
        description="Convert HardFlow score-gate-audit.ndjson to executor report format"
    )
    parser.add_argument("audit_file", type=Path, help="Path to score-gate-audit.ndjson")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSON path (default: <audit_file>.executor-report.json)",
    )
    args = parser.parse_args()

    if not args.audit_file.exists():
        print(f"[adapter] file not found: {args.audit_file}", file=sys.stderr)
        sys.exit(1)

    records = parse_ndjson(args.audit_file)
    if not records:
        print("[adapter] no valid records found in audit file", file=sys.stderr)
        sys.exit(1)

    print(f"[adapter] parsed {len(records)} audit records from {args.audit_file}")

    report = build_executor_report(records, source_path=str(args.audit_file))

    output_path = args.output or args.audit_file.with_suffix(".executor-report.json")
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[adapter] executor report written: {output_path}")
    print(f"[adapter] summary: {report['tasks_selected']} records, {report['tasks_failed']} failed")

    # 输出 gate 级别摘要
    for gate_name, info in report.get("gate_summary", {}).items():
        print(f"  {gate_name}: attempts={info['attempts']} passed={info['passed']} avg_score={info['avg_score']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""蒸馏报告器：产出 distill-report.json 和控制面桥接报告。

负责汇总一次蒸馏运行的所有产物、统计和桥接记录。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger("distill_reporter")


def build_distill_report(
    artifacts: Sequence[dict[str, Any]],
    stats: dict[str, int] | None = None,
    source: str = "",
    since_hours: int = 48,
    dry_run: bool = False,
) -> dict[str, Any]:
    """构建蒸馏报告。

    Args:
        artifacts: DistillArtifact 列表
        stats: 各类型统计
        source: 数据源
        since_hours: 回溯时间
        dry_run: 是否 dry-run

    Returns:
        完整的 distill-report 字典
    """
    # 按类型统计
    by_kind: dict[str, int] = {}
    hot_memory_writes = 0
    hot_memory_bytes_delta = 0
    duplicates_skipped = 0
    needs_review = 0
    parse_failures = 0

    for a in artifacts:
        kind = a.get("kind", "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        if a.get("target_kind") == "hot_memory":
            hot_memory_writes += 1
            hot_memory_bytes_delta += len(a.get("summary", "").encode("utf-8"))
        if a.get("requires_human_review"):
            needs_review += 1
        if a.get("confidence", 1) < 0.3:
            parse_failures += 1

    # 技能候选
    skill_candidates = [a.get("title", "") for a in artifacts if a.get("kind") == "pattern"]

    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": source,
        "since_hours": since_hours,
        "dry_run": dry_run,
        "summary": {
            "total_artifacts": len(artifacts),
            "by_kind": by_kind,
            "hot_memory_writes": hot_memory_writes,
            "hot_memory_bytes_delta": hot_memory_bytes_delta,
            "duplicates_skipped": duplicates_skipped,
            "needs_review": needs_review,
            "parse_failures": parse_failures,
        },
        "artifacts": [
            {
                "artifact_id": a.get("artifact_id", ""),
                "kind": a.get("kind", ""),
                "title": a.get("title", ""),
                "confidence": a.get("confidence", 0),
                "requires_human_review": a.get("requires_human_review", False),
            }
            for a in artifacts
        ],
        "control_plane_bridge_ids": [],
        "skill_candidates": skill_candidates,
    }

    if stats:
        report["store_stats"] = stats

    return report


def build_bridge_report(
    artifacts: Sequence[dict[str, Any]],
    workspace: str = "",
    trace_id: str = "",
    task_id: str = "",
    run_id: str = "",
) -> list[dict[str, Any]]:
    """为蒸馏产物生成控制面桥接记录。

    Args:
        artifacts: DistillArtifact 列表
        workspace: 工作区路径
        trace_id: 追溯 ID
        task_id: 任务 ID
        run_id: 执行 ID

    Returns:
        BridgeRecord 列表
    """
    bridges: list[dict[str, Any]] = []
    for i, a in enumerate(artifacts):
        aid = a.get("artifact_id", f"bridge_auto_{i:04d}")
        today = datetime.now().strftime("%Y%m%d")
        bridges.append({
            "bridge_id": f"bridge_{today}_{i+1:04d}",
            "artifact_id": aid,
            "trace_id": trace_id or a.get("trace_id", ""),
            "task_id": task_id or a.get("task_id", ""),
            "run_id": run_id or a.get("run_id", ""),
            "workspace": workspace,
            "root_cause_hints": [],
            "source_report_paths": [],
        })
    return bridges


def save_report(report: dict[str, Any], output_dir: str | Path, prefix: str = "distill") -> Path:
    """保存报告到文件。

    Args:
        report: 报告字典
        output_dir: 输出目录
        prefix: 文件前缀（distill / bridge）

    Returns:
        报告文件路径
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d")
    path = out / f"{prefix}-{ts}.json"
    # 避免覆盖已有文件
    if path.exists():
        seq = 1
        while (out / f"{prefix}-{ts}-{seq}.json").exists():
            seq += 1
        path = out / f"{prefix}-{ts}-{seq}.json"

    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("report_saved:path=%s", path)
    return path

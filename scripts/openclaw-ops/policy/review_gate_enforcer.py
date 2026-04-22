#!/usr/bin/env python3
"""
双AI审查门禁执行器。
读取对抗式审查联合结论，控制HardFlow G0-G6门禁放行。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


def setup_logging() -> logging.Logger:
    log_dir = Path(".workflow/logs/review_gate_enforcer")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger("review_gate_enforcer")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


@dataclass
class ConsensusDoc:
    final_verdict: Literal[
        "ready_for_solution",
        "ready_for_implement",
        "pass",
        "requires_revision",
        "blocked_by_unknowns",
        "dissent",
    ]
    confidence: Literal["high", "medium", "low"] = "medium"
    dissent: bool = False
    dissent_detail: str = ""
    rewrite_targets: list[str] = field(default_factory=list)
    failure_learning_triggered: bool = False
    rounds: int = 1


ALLOWED_VERDICTS = {
    "requirements": {"ready_for_solution"},
    "solution": {"ready_for_implement"},
    "code": {"pass"},
}


def parse_consensus(content: str) -> ConsensusDoc:
    """从markdown解析共识文档。"""

    def extract(pattern: str, text: str, default: str = "") -> str:
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else default

    def extract_bool(pattern: str, text: str) -> bool:
        m = re.search(pattern, text, re.IGNORECASE)
        return m is not None and "true" in m.group(1).lower()

    def extract_list(pattern: str, text: str) -> list[str]:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if not m:
            return []
        items = re.findall(r"[-*]\s*(.+)", m.group(1))
        return [i.strip() for i in items]

    verdict = extract(r"(?:最终裁决\s*[:：]\s*|裁决\s*[:：]\s*)(\w+)", content, "dissent")
    all_verdicts = set()
    for v in ALLOWED_VERDICTS.values():
        all_verdicts |= v
    all_verdicts |= {"requires_revision", "blocked_by_unknowns", "dissent"}
    if verdict not in all_verdicts:
        verdict = "dissent"

    confidence = extract(r"置信度\s*[:：]\s*(\w+)", content, "medium")
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    return ConsensusDoc(
        final_verdict=verdict,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        dissent=extract_bool(r"分歧标记\s*[:：]\s*(\w+)", content),
        dissent_detail=extract(r"分歧点\s*[:：]\s*(.+?)(?:\n|$)", content),
        rewrite_targets=extract_list(r"回写目标.*?\n(.*?)(?:##|$)", content),
        failure_learning_triggered=extract_bool(r"失败学习触发\s*[:：]\s*(\w+)", content),
        rounds=int(extract(r"讨论轮次\s*[:：]\s*(\d+)", content, "1")) or 1,
    )


def check_gate(
    task_id: str,
    review_type: str,
    consensus: ConsensusDoc,
    expected_verdict: str | None = None,
) -> dict:
    """检查门禁，返回结果字典。"""

    allowed = ALLOWED_VERDICTS.get(review_type, set())

    if consensus.final_verdict not in allowed and consensus.final_verdict not in (
        "requires_revision",
        "blocked_by_unknowns",
        "dissent",
    ):
        return {
            "task_id": task_id,
            "gate_allowed": False,
            "error_code": "unknown_verdict",
            "verdict": consensus.final_verdict,
            "review_type": review_type,
            "next_action": "invalid_review",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    if consensus.final_verdict not in allowed:
        error_map = {
            "requires_revision": ("requires_revision", "rewrite_docs"),
            "blocked_by_unknowns": ("blocked", "halt_and_investigate"),
            "dissent": ("dissent", "human_arbitration_required"),
        }
        error_code, next_action = error_map.get(
            consensus.final_verdict, ("unknown", "invalid")
        )
        return {
            "task_id": task_id,
            "gate_allowed": False,
            "error_code": error_code,
            "verdict": consensus.final_verdict,
            "confidence": consensus.confidence,
            "dissent": consensus.dissent,
            "dissent_detail": consensus.dissent_detail,
            "review_type": review_type,
            "next_action": next_action,
            "rewrite_targets": consensus.rewrite_targets,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    if expected_verdict and consensus.final_verdict != expected_verdict:
        return {
            "task_id": task_id,
            "gate_allowed": False,
            "error_code": "mismatch",
            "verdict": consensus.final_verdict,
            "expected": expected_verdict,
            "review_type": review_type,
            "next_action": "review_mismatch",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "task_id": task_id,
        "gate_allowed": True,
        "verdict": consensus.final_verdict,
        "confidence": consensus.confidence,
        "dissent": consensus.dissent,
        "review_type": review_type,
        "next_action": f"proceed_to_next_gate",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="双AI审查门禁执行器")
    parser.add_argument("--task-id", required=True, help="任务唯一标识")
    parser.add_argument(
        "--review-type",
        required=True,
        choices=["requirements", "solution", "code"],
        help="审查类型",
    )
    parser.add_argument("--review-path", required=True, help="consensus.md 路径")
    parser.add_argument(
        "--expected-verdict",
        choices=["ready_for_solution", "ready_for_implement", "pass"],
        help="期望结论",
    )
    parser.add_argument("--dry-run", action="store_true", help="只检查不执行")
    args = parser.parse_args(argv)

    logger = setup_logging()
    logger.info(
        "开始检查 task=%s type=%s path=%s",
        args.task_id,
        args.review_type,
        args.review_path,
    )

    review_path = Path(args.review_path)
    if not review_path.exists():
        result = {
            "task_id": args.task_id,
            "gate_allowed": False,
            "error_code": "missing_review",
            "review_path": str(review_path),
            "next_action": "invalid",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    content = review_path.read_text(encoding="utf-8")
    try:
        consensus = parse_consensus(content)
    except Exception as exc:
        logger.exception("解析 consensus 失败")
        result = {
            "task_id": args.task_id,
            "gate_allowed": False,
            "error_code": "invalid_format",
            "detail": str(exc),
            "next_action": "invalid",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    result = check_gate(
        args.task_id,
        args.review_type,
        consensus,
        args.expected_verdict,
    )

    logger.info(
        "检查结果 allowed=%s verdict=%s",
        result.get("gate_allowed"),
        result.get("verdict"),
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("gate_allowed") else 1


if __name__ == "__main__":
    raise SystemExit(main())

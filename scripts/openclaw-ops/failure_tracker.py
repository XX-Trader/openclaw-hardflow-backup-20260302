#!/usr/bin/env python3
"""
失败次数跟踪器。
检测同类任务连续失败，触发失败学习流程。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

# 跨平台文件锁
try:
    import fcntl

    def _lock(fh, lock_type: int) -> None:
        fcntl.flock(fh.fileno(), lock_type)

    LOCK_SH = fcntl.LOCK_SH
    LOCK_EX = fcntl.LOCK_EX
    LOCK_UN = fcntl.LOCK_UN
except ImportError:
    # Windows: fcntl 不可用，使用 noop 锁（单机场景下并发风险低）
    LOCK_SH = 0
    LOCK_EX = 0
    LOCK_UN = 0

    def _lock(_fh, _lock_type: int) -> None:
        pass


def setup_logging() -> logging.Logger:
    log_dir = Path(".workflow/logs/failure_tracker")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger("failure_tracker")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


DATA_DIR = Path(".workflow/failure-tracking")
RECORDS_FILE = DATA_DIR / "failures.ndjson"


@dataclass
class FailureRecord:
    record_id: str
    task_id: str
    task_type: str
    model: str
    project_key: str | None
    failure_reason: str
    root_cause: str | None = None
    review_path: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved: bool = False
    resolved_at: str | None = None
    resolution: str | None = None


class FailureStore:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RECORDS_FILE.touch(exist_ok=True)

    def _lock_and_read(self) -> list[dict]:
        with open(RECORDS_FILE, "r", encoding="utf-8") as fh:
            _lock(fh, LOCK_SH)
            try:
                lines = [json.loads(line) for line in fh if line.strip()]
            finally:
                _lock(fh, LOCK_UN)
        return lines

    def _lock_and_append(self, record: dict) -> None:
        with open(RECORDS_FILE, "a", encoding="utf-8") as fh:
            _lock(fh, LOCK_EX)
            try:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            finally:
                _lock(fh, LOCK_UN)

    def add(self, record: FailureRecord) -> None:
        self._lock_and_append(asdict(record))

    def query(
        self,
        task_type: str | None = None,
        model: str | None = None,
        project_key: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        lines = self._lock_and_read()
        results: list[dict] = []
        for line in reversed(lines):
            if task_type and line.get("task_type") != task_type:
                continue
            if model and line.get("model") != model:
                continue
            if project_key and line.get("project_key") != project_key:
                continue
            results.append(line)
            if len(results) >= limit:
                break
        return results

    def check_trigger(
        self,
        task_type: str,
        model: str | None = None,
        project_key: str | None = None,
        consecutive: int = 2,
        hours: int = 168,
    ) -> dict:
        lines = self._lock_and_read()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        matched: list[dict] = []
        for line in reversed(lines):
            ts_str = line["timestamp"].replace("Z", "+00:00")
            ts = datetime.fromisoformat(ts_str)
            if ts < cutoff:
                break
            if line.get("task_type") != task_type:
                continue
            if model and line.get("model") != model:
                continue
            if project_key and line.get("project_key") != project_key:
                continue
            if line.get("resolved"):
                continue
            matched.append(line)

        triggered = len(matched) >= consecutive
        return {
            "task_type": task_type,
            "triggered": triggered,
            "consecutive_failures": len(matched),
            "records": matched[:consecutive],
            "suggested_action": "trigger_failure_learning" if triggered else "none",
        }

    def cleanup(self, days: int = 30) -> int:
        lines = self._lock_and_read()
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        kept = [
            line
            for line in lines
            if datetime.fromisoformat(line["timestamp"].replace("Z", "+00:00"))
            >= cutoff
        ]
        with open(RECORDS_FILE, "w", encoding="utf-8") as fh:
            _lock(fh, LOCK_EX)
            try:
                for line in kept:
                    fh.write(json.dumps(line, ensure_ascii=False) + "\n")
            finally:
                _lock(fh, LOCK_UN)
        return len(lines) - len(kept)


def cmd_check(args: argparse.Namespace) -> int:
    store = FailureStore()
    result = store.check_trigger(
        args.task_type,
        args.model,
        args.project_key,
        args.consecutive,
        args.hours,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    store = FailureStore()
    record = FailureRecord(
        record_id=f"rec-{uuid.uuid4().hex[:8]}",
        task_id=args.task_id,
        task_type=args.task_type,
        model=args.model,
        project_key=args.project_key,
        failure_reason=args.failure_reason,
        root_cause=args.root_cause,
        review_path=args.review_path,
    )
    store.add(record)
    print(json.dumps({"status": "recorded", "record_id": record.record_id}, ensure_ascii=False))
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    store = FailureStore()
    results = store.query(args.task_type, args.model, args.project_key, args.limit)
    print(json.dumps({"records": results}, ensure_ascii=False, indent=2))
    return 0


def cmd_cleanup(args: argparse.Namespace) -> int:
    store = FailureStore()
    removed = store.cleanup(args.days)
    print(json.dumps({"removed": removed}, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="失败次数跟踪器")
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="检测是否触发失败学习")
    p_check.add_argument("--task-type", required=True)
    p_check.add_argument("--model")
    p_check.add_argument("--project-key")
    p_check.add_argument("--consecutive", type=int, default=2)
    p_check.add_argument("--hours", type=int, default=168)
    p_check.set_defaults(func=cmd_check)

    p_record = sub.add_parser("record", help="记录一次失败")
    p_record.add_argument("--task-id", required=True)
    p_record.add_argument("--task-type", required=True)
    p_record.add_argument("--model", required=True)
    p_record.add_argument("--failure-reason", required=True)
    p_record.add_argument("--project-key")
    p_record.add_argument("--root-cause")
    p_record.add_argument("--review-path")
    p_record.set_defaults(func=cmd_record)

    p_query = sub.add_parser("query", help="查询历史记录")
    p_query.add_argument("--task-type")
    p_query.add_argument("--model")
    p_query.add_argument("--project-key")
    p_query.add_argument("--limit", type=int, default=10)
    p_query.set_defaults(func=cmd_query)

    p_cleanup = sub.add_parser("cleanup", help="清理过期记录")
    p_cleanup.add_argument("--days", type=int, default=30)
    p_cleanup.set_defaults(func=cmd_cleanup)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

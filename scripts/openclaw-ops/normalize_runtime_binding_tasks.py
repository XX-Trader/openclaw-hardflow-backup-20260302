#!/usr/bin/env python3
"""Normalize legacy runtime-binding tasks so they do not stay in executable backlog."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc
RUNTIME_BINDING_TYPE = "ops_runtime_cron"
RUNTIME_BINDING_ACTION = "runtime_binding"
LEGACY_BACKLOG_STATUSES = ("pending", "running", "failed", "escalated")


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def normalize_runtime_binding_tasks(db_path: Path, *, dry_run: bool = False) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "ok": False,
            "db": str(db_path),
            "error": f"db_missing:{db_path}",
            "updated_count": 0,
            "updated_task_ids": [],
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT task_id, status, action, completed_at, updated_at
            FROM tasks
            WHERE task_type = ?
              AND LOWER(status) IN (?, ?, ?, ?)
            ORDER BY updated_at ASC, created_at ASC
            """,
            (RUNTIME_BINDING_TYPE, *LEGACY_BACKLOG_STATUSES),
        ).fetchall()
        task_ids = [str(row["task_id"]) for row in rows]
        if dry_run or not task_ids:
            return {
                "ok": True,
                "db": str(db_path),
                "dry_run": bool(dry_run),
                "updated_count": len(task_ids),
                "updated_task_ids": task_ids,
            }

        with conn:
            for row in rows:
                completed_at = (
                    str(row["completed_at"] or "").strip()
                    or str(row["updated_at"] or "").strip()
                    or now_iso()
                )
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'passed',
                        action = ?,
                        completed_at = ?
                    WHERE task_id = ?
                    """,
                    (RUNTIME_BINDING_ACTION, completed_at, str(row["task_id"])),
                )
        return {
            "ok": True,
            "db": str(db_path),
            "dry_run": False,
            "updated_count": len(task_ids),
            "updated_task_ids": task_ids,
        }
    finally:
        conn.close()


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Normalize legacy runtime binding task statuses")
    parser.add_argument("--db", default=str(home / ".openclaw/ops/task-center/task_center.db"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    result = normalize_runtime_binding_tasks(Path(args.db).expanduser(), dry_run=bool(args.dry_run))
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"ok={str(bool(result.get('ok'))).lower()}")
        print(f"db={result.get('db', '')}")
        print(f"dry_run={str(bool(result.get('dry_run'))).lower()}")
        print(f"updated_count={int(result.get('updated_count', 0) or 0)}")
        for task_id in result.get("updated_task_ids", []) or []:
            print(f"updated_task_id={task_id}")
        if result.get("error"):
            print(f"error={result['error']}")
    return 0 if bool(result.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())

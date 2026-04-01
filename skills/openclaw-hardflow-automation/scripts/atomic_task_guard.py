#!/usr/bin/env python3
"""Ensure .workflow/task.json stays atomic and execution-ready."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

ACTION_HINTS = (
    "define",
    "implement",
    "build",
    "write",
    "run",
    "validate",
    "integrate",
    "定义",
    "实现",
    "编写",
    "验证",
    "联调",
)


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def infer_items(task_text: str) -> list[dict[str, str]]:
    text = (task_text or "").strip() or "atomic hardflow task"
    lower = text.lower()
    backend_owner = "backend-dev"
    frontend_owner = "frontend-dev"

    data_title = "Define database schema and API contract"
    backend_title = "Implement backend endpoints and business logic"
    frontend_title = "Build frontend components and interaction flow"
    integrate_title = "Run API-UI integration and real-browser E2E validation"

    if "frontend" not in lower and "前端" not in lower and "ui" not in lower:
        frontend_title = "Build operator/UI touchpoints required by this task"
    if "backend" not in lower and "后端" not in lower and "api" not in lower:
        backend_title = "Implement core logic and callable interface"
        data_title = "Define data contract and persistence strategy"

    return [
        {
            "id": "t01-define-contract",
            "title": data_title,
            "owner": backend_owner,
            "status": "pending",
            "deliverable": "schema or contract diff with explicit fields",
            "acceptance": "input/output fields and failure paths are documented",
        },
        {
            "id": "t02-backend-impl",
            "title": backend_title,
            "owner": backend_owner,
            "status": "pending",
            "deliverable": "backend code and runnable endpoint",
            "acceptance": "unit or API checks pass for changed behavior",
        },
        {
            "id": "t03-frontend-impl",
            "title": frontend_title,
            "owner": frontend_owner,
            "status": "pending",
            "deliverable": "frontend or operator-side invocation path",
            "acceptance": "UI flow can trigger backend and render result",
        },
        {
            "id": "t04-integration",
            "title": integrate_title,
            "owner": "tester",
            "status": "pending",
            "deliverable": "integration log + screenshot evidence",
            "acceptance": "real-browser E2E passes with visual confirmation",
        },
    ]


def generate_atomic_task(task_text: str) -> dict[str, Any]:
    return {
        "schema_version": "2026-03-03",
        "task": (task_text or "").strip(),
        "updated_at": now_iso(),
        "items": infer_items(task_text),
    }


def validate_atomic_task(payload: dict[str, Any], min_items: int) -> list[str]:
    errors: list[str] = []
    items = payload.get("items")
    if not isinstance(items, list):
        return ["items must be a list"]
    if len(items) < min_items:
        errors.append(f"items count must be >= {min_items}")
        return errors

    seen_ids: set[str] = set()
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"items[{idx}] must be an object")
            continue
        item_id = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        owner = str(item.get("owner", "")).strip()
        if not item_id:
            errors.append(f"items[{idx}].id is required")
        elif item_id in seen_ids:
            errors.append(f"items[{idx}].id is duplicated: {item_id}")
        else:
            seen_ids.add(item_id)
        if not title:
            errors.append(f"items[{idx}].title is required")
        elif len(title) < 8:
            errors.append(f"items[{idx}].title too short")
        elif not any(hint in title.lower() for hint in ACTION_HINTS):
            errors.append(f"items[{idx}].title is not atomic/actionable: {title}")
        if not owner:
            errors.append(f"items[{idx}].owner is required")
        if str(item.get("status", "")).strip() not in {"pending", "running", "done", "blocked"}:
            errors.append(f"items[{idx}].status must be pending|running|done|blocked")
        if not str(item.get("deliverable", "")).strip():
            errors.append(f"items[{idx}].deliverable is required")
        if not str(item.get("acceptance", "")).strip():
            errors.append(f"items[{idx}].acceptance is required")
    return errors


def write_atomic_task(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure task.json is atomic")
    parser.add_argument("--task-file", default=".workflow/task.json")
    parser.add_argument("--task-text", default="")
    parser.add_argument("--min-items", type=int, default=4)
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    task_file = Path(args.task_file).expanduser()
    min_items = max(1, int(args.min_items))
    task_text = str(args.task_text or "").strip()

    existed = task_file.exists()
    payload = load_json(task_file)
    action = "kept"

    if not isinstance(payload, dict):
        payload = generate_atomic_task(task_text)
        write_atomic_task(task_file, payload)
        action = "created" if not existed else "rewritten"
    else:
        errors = validate_atomic_task(payload, min_items=min_items)
        if errors:
            payload = generate_atomic_task(task_text)
            write_atomic_task(task_file, payload)
            action = "rewritten"

    errors_after = validate_atomic_task(payload, min_items=min_items)
    ok = len(errors_after) == 0
    result = {
        "ok": ok,
        "action": action,
        "task_file": str(task_file),
        "item_count": len(payload.get("items", [])) if isinstance(payload.get("items"), list) else 0,
        "errors": errors_after,
    }
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

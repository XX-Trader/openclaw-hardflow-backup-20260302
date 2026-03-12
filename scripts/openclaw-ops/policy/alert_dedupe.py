#!/usr/bin/env python3
"""Shared alert dedupe helpers for ops cron and task executor."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


UTC = timezone.utc
WORKFLOW_FAILURE_BUCKET = "workflow_failure"
WORKFLOW_TASK_RE = re.compile(r"^todo-ops-workflow-repair-(?P<slug>.+)-[0-9a-f]{10}$")
WORKFLOW_ID_PATTERNS = (
    re.compile(r"workflow_job_id[:=]\s*([A-Za-z0-9._:-]+)", re.IGNORECASE),
    re.compile(r"ops_cron_runner::([A-Za-z0-9._:-]+)", re.IGNORECASE),
    re.compile(r"job_id[=:]\s*([A-Za-z0-9._:-]+)", re.IGNORECASE),
)


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def safe_slug(value: Any, max_len: int = 24) -> str:
    out = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip())
    out = out.strip("-._")
    return (out[:max_len] or "unknown")


def _uniq_tokens(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        token = safe_slug(raw)
        if not token or token == "unknown" or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return sorted(out)


def resolve_shared_alert_state_path(value: str | Path | None = None) -> Path:
    raw = str(value or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".openclaw" / "ops" / "alert-dedupe-state.json"


def default_dedupe_state() -> dict[str, Any]:
    return {
        "schema_version": "2026-03-12",
        "updated_at": "",
        "buckets": {},
    }


def load_dedupe_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_dedupe_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default_dedupe_state()
    return payload if isinstance(payload, dict) else default_dedupe_state()


def save_dedupe_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def workflow_tokens_from_job_ids(job_ids: Iterable[Any]) -> list[str]:
    return _uniq_tokens(job_ids)


def extract_workflow_failure_tokens_from_task(
    task_id: Any = "",
    *,
    task_type: Any = "",
    requirement: Any = "",
    context_payload: Any = None,
) -> list[str]:
    tokens: list[str] = []
    if isinstance(context_payload, dict):
        for key in ("operation_path", "location", "problem", "scope", "full_background", "evidence"):
            value = str(context_payload.get(key, "")).strip()
            if not value:
                continue
            for pattern in WORKFLOW_ID_PATTERNS:
                for match in pattern.findall(value):
                    tokens.append(match)
    requirement_text = str(requirement or "").strip()
    if requirement_text:
        for pattern in WORKFLOW_ID_PATTERNS:
            for match in pattern.findall(requirement_text):
                tokens.append(match)
    if not tokens and (str(task_type or "").strip() == "ops_workflow_repair" or str(task_id or "").strip()):
        match = WORKFLOW_TASK_RE.match(str(task_id or "").strip())
        if match:
            tokens.append(match.group("slug"))
    return _uniq_tokens(tokens)


def build_workflow_failure_signature(tokens: Iterable[Any]) -> str:
    normalized = _uniq_tokens(tokens)
    if not normalized:
        return ""
    raw = json.dumps({"bucket": WORKFLOW_FAILURE_BUCKET, "tokens": normalized}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def check_and_record_signature(
    state: dict[str, Any],
    *,
    bucket: str,
    signature: str,
    now_text: str = "",
    cooldown_minutes: int = 60,
    meta: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    normalized_bucket = str(bucket or "").strip() or "default"
    normalized_signature = str(signature or "").strip()
    if not normalized_signature:
        return False, ""

    current_at = parse_iso(now_text) or datetime.now(tz=UTC)
    cooldown = max(1, int(cooldown_minutes or 60))
    buckets = state.get("buckets", {})
    if not isinstance(buckets, dict):
        buckets = {}
    bucket_state = buckets.get(normalized_bucket, {})
    if not isinstance(bucket_state, dict):
        bucket_state = {}

    keep_after = current_at - timedelta(days=7)
    for key, item in list(bucket_state.items()):
        last_at = parse_iso(item.get("notified_at") if isinstance(item, dict) else "")
        if last_at and last_at >= keep_after:
            continue
        bucket_state.pop(key, None)

    existing = bucket_state.get(normalized_signature, {})
    last_notified = parse_iso(existing.get("notified_at") if isinstance(existing, dict) else "")
    if last_notified and (current_at - last_notified) < timedelta(minutes=cooldown):
        if normalized_bucket == WORKFLOW_FAILURE_BUCKET:
            return True, f"workflow_repeat_within_cooldown:{cooldown}m"
        return True, f"signature_repeat_within_cooldown:{cooldown}m"

    record = {
        "notified_at": current_at.replace(microsecond=0).isoformat(),
    }
    if isinstance(meta, dict):
        for key, value in meta.items():
            record[str(key)] = value
    bucket_state[normalized_signature] = record
    buckets[normalized_bucket] = bucket_state
    state["buckets"] = buckets
    state["updated_at"] = current_at.replace(microsecond=0).isoformat()
    return False, ""

"""Utility functions and types for the Policy Enforcer."""

from __future__ import annotations

import json
import os
import sys
from dataclass_compat import compat_dataclass as dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

GOVERNANCE_BRIDGE_EPILOG = (
    "Bridge contract: keep governance logic in Python, trigger it via official "
    "OpenClaw cron/hooks/webhook surfaces, return structured JSON or NO_REPLY, "
    "and do not mutate vendor private runtime state files directly."
)

class PolicyError(RuntimeError):
    """Raised on policy violations."""


@dataclass(slots=True)
class RuntimePaths:
    db: Path
    policy_file: Path
    routing_file: Path
    pricing_file: Path


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    norm = str(value).strip().lower()
    if norm == "":
        return default
    return norm in {"1", "true", "yes", "y", "on"}


def has_context_value(value: Any) -> bool:
    if isinstance(value, list):
        return any(has_context_value(v) for v in value)
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    if lowered in {"none", "n/a", "na", "unknown", "-", "未提供", "待补充"}:
        return False
    return True


def get_context_field_value(payload: dict[str, Any], field_path: str) -> Any:
    if not isinstance(payload, dict):
        return None
    normalized_path = str(field_path or "").strip()
    if not normalized_path:
        return None
    if normalized_path in payload:
        return payload.get(normalized_path)
    current: Any = payload
    for segment in normalized_path.split("."):
        key = str(segment or "").strip()
        if not key or not isinstance(current, dict) or key not in current:
            return None
        current = current.get(key)
    return current


def emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def runtime_defaults() -> dict[str, str]:
    script_policy_dir = Path(__file__).resolve().parent
    openclaw_home = Path(
        os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw"))
    ).expanduser()

    default_task_center_dir = Path(".workflow/task-center")
    if "TASK_CENTER_DIR" in os.environ:
        task_center_dir = Path(os.environ["TASK_CENTER_DIR"]).expanduser()
    elif default_task_center_dir.exists():
        task_center_dir = default_task_center_dir
    else:
        task_center_dir = Path(openclaw_home / "ops" / "task-center")

    if "OPENCLAW_POLICY_ROOT" in os.environ:
        policy_runtime_dir = Path(os.environ["OPENCLAW_POLICY_ROOT"]).expanduser()
    elif (script_policy_dir / "policy-config.json").exists():
        policy_runtime_dir = script_policy_dir
    else:
        policy_runtime_dir = Path(openclaw_home / "ops" / "policy")

    pricing_file = (
        os.environ.get("POLICY_PRICING_FILE")
        or os.environ.get("TOKEN_PRICING_FILE")
        or str(policy_runtime_dir / "token-pricing.json")
    )
    return {
        "db": os.environ.get("POLICY_DB_FILE", str(task_center_dir / "task_center.db")),
        "policy_file": os.environ.get("POLICY_FILE", str(policy_runtime_dir / "policy-config.json")),
        "routing_file": os.environ.get("POLICY_ROUTING_FILE", str(policy_runtime_dir / "routing-rules.json")),
        "pricing_file": pricing_file,
        "openclaw_config": os.environ.get("OPENCLAW_CONFIG", str(openclaw_home / "openclaw.json")),
        "project_registry": os.environ.get("PROJECT_REGISTRY", str(task_center_dir / "project-registry.json")),
    }


def read_json(path: Path, default: dict[str, Any] | None = None, write_if_missing: bool = False) -> dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise PolicyError(f"json object expected: {path}")
        return data

    if default is None:
        raise PolicyError(f"missing file: {path}")

    data = json.loads(json.dumps(default))
    if write_if_missing:
        write_json_atomic(
            path,
            data,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
    return data


def merge_missing_keys(base: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base))
    for key, value in defaults.items():
        if key not in out:
            out[key] = json.loads(json.dumps(value))
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_missing_keys(out[key], value)
    return out


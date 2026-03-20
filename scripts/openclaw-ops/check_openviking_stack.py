#!/usr/bin/env python3
"""Validate the OpenViking service/plugin/routing stack for the current runtime."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc


def now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def load_json_file(path: Path) -> dict[str, Any]:
    """Load a JSON file as a dict, failing fast on invalid payloads."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"config root must be object: {path}")
    return data


def candidate_config_paths(explicit_path: str | None) -> list[Path]:
    """Return candidate runtime config paths in priority order."""
    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())

    openclaw_home = os.environ.get("OPENCLAW_HOME", "").strip()
    if openclaw_home:
        candidates.append(Path(openclaw_home).expanduser() / "openclaw.json")

    home = os.environ.get("HOME", "").strip()
    if home:
        candidates.append(Path(home).expanduser() / ".openclaw" / "openclaw.json")

    user_profile = os.environ.get("USERPROFILE", "").strip()
    if user_profile:
        candidates.append(Path(user_profile).expanduser() / ".openclaw" / "openclaw.json")

    deduped: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def resolve_config_path(explicit_path: str | None) -> Path | None:
    """Resolve the first existing runtime config path."""
    for candidate in candidate_config_paths(explicit_path):
        if candidate.exists():
            return candidate.resolve()
    return None


def normalize_string_list(value: Any) -> list[str]:
    """Normalize a mixed value into a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def normalize_string(value: Any) -> str:
    """Normalize any scalar value into a stripped string."""
    if value is None:
        return ""
    return str(value).strip()


def parse_int(value: Any) -> int | None:
    """Parse a positive integer from a mixed scalar value."""
    text = normalize_string(value)
    if not text:
        return None
    try:
        parsed = int(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def memory_openviking_runtime_config(memory_entry: dict[str, Any]) -> dict[str, Any]:
    """Return the normalized runtime config for the memory-openviking plugin entry."""
    raw_config = memory_entry.get("config")
    config = raw_config if isinstance(raw_config, dict) else {}
    return {
        "mode": normalize_string(config.get("mode") or memory_entry.get("mode")),
        "config_path": normalize_string(config.get("configPath") or memory_entry.get("configPath")),
        "port": parse_int(config.get("port") or memory_entry.get("port")),
        "health_url": normalize_string(config.get("healthUrl") or config.get("health_url") or memory_entry.get("healthUrl") or memory_entry.get("health_url")),
        "base_url": normalize_string(config.get("baseUrl") or config.get("base_url") or memory_entry.get("baseUrl") or memory_entry.get("base_url")),
    }


def derive_stack_state(config: dict[str, Any]) -> dict[str, Any]:
    """Derive OpenViking service/plugin/routing state from runtime config."""
    plugins = config.get("plugins")
    if not isinstance(plugins, dict):
        plugins = {}

    entries = plugins.get("entries")
    if not isinstance(entries, dict):
        entries = {}

    slots = plugins.get("slots")
    if not isinstance(slots, dict):
        slots = {}

    allow = normalize_string_list(plugins.get("allow"))
    memory_entry = entries.get("memory-openviking")
    if not isinstance(memory_entry, dict):
        memory_entry = {}
    memory_runtime = memory_openviking_runtime_config(memory_entry)

    slot_memory = str(slots.get("memory", "")).strip()
    allow_contains = "memory-openviking" in allow
    entry_enabled = bool(memory_entry.get("enabled"))

    mode = "official-default"
    if slot_memory == "memory-openviking" or allow_contains or entry_enabled:
        mode = "openviking"

    if mode == "openviking":
        routing_ok = slot_memory == "memory-openviking"
        plugin_ok = entry_enabled or allow_contains or slot_memory == "memory-openviking"
        allow_ok = (not allow) or allow_contains
    else:
        routing_ok = slot_memory in {"", "memory-core"}
        plugin_ok = True
        allow_ok = True

    return {
        "mode": mode,
        "routing_layer": {
            "slot_memory": slot_memory,
            "slot_expected": "memory-openviking" if mode == "openviking" else "memory-core|empty",
            "passed": routing_ok,
        },
        "plugin_layer": {
            "entry_enabled": entry_enabled,
            "allow_list": allow,
            "allow_contains": allow_contains,
            "allow_passed": allow_ok,
            "runtime_mode": memory_runtime["mode"],
            "runtime_config_path": memory_runtime["config_path"],
            "runtime_port": memory_runtime["port"],
            "passed": plugin_ok and allow_ok,
        },
        "memory_runtime": memory_runtime,
    }


def resolve_health_url(explicit_url: str | None, memory_runtime: dict[str, Any]) -> str:
    """Resolve the OpenViking health check URL."""
    if explicit_url:
        return explicit_url
    health_url = os.environ.get("OPENVIKING_HEALTH_URL", "").strip()
    if health_url:
        return health_url
    runtime_health_url = normalize_string(memory_runtime.get("health_url"))
    if runtime_health_url:
        return runtime_health_url
    runtime_base_url = normalize_string(memory_runtime.get("base_url"))
    if runtime_base_url:
        return runtime_base_url.rstrip("/") + "/health"
    runtime_port = parse_int(memory_runtime.get("port"))
    if runtime_port is not None:
        return f"http://127.0.0.1:{runtime_port}/health"
    base_url = os.environ.get("OPENVIKING_BASE_URL", "").strip()
    if base_url:
        return base_url.rstrip("/") + "/health"
    return "http://127.0.0.1:1933/health"


def check_health(url: str, timeout_seconds: float) -> dict[str, Any]:
    """Check the OpenViking health endpoint and return structured evidence."""
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {
                "url": url,
                "http_status": int(response.status),
                "body": body,
                "passed": 200 <= int(response.status) < 300,
            }
    except urllib.error.URLError as exc:
        return {
            "url": url,
            "error": str(exc),
            "passed": False,
        }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a UTF-8 JSON payload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_gate(gate_path: Path, run_id: str, passed: bool, reason: str) -> None:
    """Write a gate file for the current run."""
    payload = {
        "passed": bool(passed),
        "updated_at": now_iso(),
        "run_id": run_id,
        "reason": reason,
    }
    write_json(gate_path, payload)


def main() -> int:
    """CLI entrypoint for OpenViking stack validation."""
    parser = argparse.ArgumentParser(description="Validate OpenViking runtime stack")
    parser.add_argument("--workspace-root", default=".", help="repo/workspace root for .workflow outputs")
    parser.add_argument("--run-id", default="", help="current workflow run id")
    parser.add_argument("--config", default="", help="explicit openclaw.json path")
    parser.add_argument("--health-url", default="", help="explicit OpenViking health URL")
    parser.add_argument("--timeout-seconds", type=float, default=5.0, help="health check timeout seconds")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    workflow_dir = workspace_root / ".workflow"
    state_file = workflow_dir / "current_run_id"
    run_id = str(args.run_id).strip() or (
        state_file.read_text(encoding="utf-8-sig").strip() if state_file.exists() else datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    run_dir = workflow_dir / "runs" / run_id
    output_file = run_dir / "acceptance" / "openviking-stack.json"
    gate_file = workflow_dir / "gates" / "openviking_stack.json"

    config_path = resolve_config_path(str(args.config).strip() or None)
    if config_path is None:
        payload = {
            "run_id": run_id,
            "passed": False,
            "updated_at": now_iso(),
            "reason": "openclaw runtime config not found",
            "candidates": [str(path) for path in candidate_config_paths(str(args.config).strip() or None)],
        }
        write_json(output_file, payload)
        write_gate(gate_file, run_id, False, payload["reason"])
        print(json.dumps(payload, ensure_ascii=False))
        return 1

    config = load_json_file(config_path)
    stack_state = derive_stack_state(config)
    health_url = resolve_health_url(str(args.health_url).strip() or None, stack_state.get("memory_runtime", {}))

    if stack_state["mode"] == "openviking":
        service_layer = check_health(health_url, timeout_seconds=float(args.timeout_seconds))
    else:
        service_layer = {
            "url": health_url,
            "passed": True,
            "skipped": True,
            "reason": "memory mode is official-default; OpenViking service not required",
        }

    passed = bool(
        stack_state["routing_layer"]["passed"]
        and stack_state["plugin_layer"]["passed"]
        and service_layer["passed"]
    )

    reason = "openviking stack passed"
    if not passed:
        reason = (
            "openviking stack failed: "
            f"mode={stack_state['mode']}, "
            f"routing={stack_state['routing_layer']['passed']}, "
            f"plugin={stack_state['plugin_layer']['passed']}, "
            f"service={service_layer['passed']}"
        )

    payload = {
        "run_id": run_id,
        "passed": passed,
        "updated_at": now_iso(),
        "config_path": str(config_path),
        "mode": stack_state["mode"],
        "service_layer": service_layer,
        "plugin_layer": stack_state["plugin_layer"],
        "routing_layer": stack_state["routing_layer"],
    }
    write_json(output_file, payload)
    write_gate(gate_file, run_id, passed, reason)
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

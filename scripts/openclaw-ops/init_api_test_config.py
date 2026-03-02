#!/usr/bin/env python3
"""Initialize API test config for OpenClaw ops audit jobs."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def default_config(base_url: str) -> dict[str, Any]:
    root = base_url.rstrip("/")
    return {
        "engine": "playwright",
        "default_timeout_seconds": 12,
        "freshness_default_max_age_seconds": 300,
        "endpoints": [
            {
                "id": "health",
                "url": f"{root}/health",
                "method": "GET",
                "risk_level": "low",
                "expect_json": True,
                "require_non_empty": True,
            },
            {
                "id": "market-snapshot",
                "url": f"{root}/api/market/snapshot",
                "method": "GET",
                "risk_level": "high",
                "expect_json": True,
                "require_non_empty": True,
                "freshness_field": "data.ts",
                "freshness_max_age_seconds": 120,
            },
        ],
        "browser_checks": [
            {
                "id": "dashboard",
                "url": f"{root}/dashboard",
                "risk_level": "high",
                "expect_text": "在线",
            }
        ],
        "notes": [
            "Replace placeholder endpoints with real production APIs.",
            "Use risk_level=high for core data and contract-sensitive endpoints.",
            "Set freshness_field and freshness_max_age_seconds for time-sensitive data.",
        ],
    }


def merge_existing(existing: dict[str, Any], generated: dict[str, Any]) -> dict[str, Any]:
    out = dict(generated)
    for key in ("engine", "default_timeout_seconds", "freshness_default_max_age_seconds"):
        if key in existing:
            out[key] = existing[key]
    if isinstance(existing.get("endpoints"), list) and existing.get("endpoints"):
        out["endpoints"] = existing["endpoints"]
    if isinstance(existing.get("browser_checks"), list) and existing.get("browser_checks"):
        out["browser_checks"] = existing["browser_checks"]
    return out


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Initialize api-test-config.json")
    parser.add_argument("--output-file", default=str(home / ".openclaw/ops/api-test-config.json"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8845")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--merge-existing", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    output_file = Path(args.output_file).expanduser()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    generated = default_config(str(args.base_url or "http://127.0.0.1:8845"))

    existed = output_file.exists()
    action = "created"
    payload = generated

    if existed and not bool(args.force):
        if bool(args.merge_existing):
            try:
                current = json.loads(output_file.read_text(encoding="utf-8-sig"))
            except Exception:
                current = {}
            if isinstance(current, dict):
                payload = merge_existing(current, generated)
            action = "merged"
        else:
            result = {
                "ok": True,
                "output_file": str(output_file),
                "action": "skipped",
                "reason": "exists",
                "generated_at": now_iso(),
            }
            if args.emit_json:
                print(json.dumps(result, ensure_ascii=False))
            else:
                print(f"output_file={result['output_file']}")
                print("action=skipped")
                print("reason=exists")
            return 0
    elif existed and bool(args.force):
        action = "overwritten"

    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {
        "ok": True,
        "output_file": str(output_file),
        "action": action,
        "generated_at": now_iso(),
        "endpoint_count": len(payload.get("endpoints", [])) if isinstance(payload.get("endpoints"), list) else 0,
        "browser_check_count": (
            len(payload.get("browser_checks", [])) if isinstance(payload.get("browser_checks"), list) else 0
        ),
    }
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"output_file={result['output_file']}")
        print(f"action={result['action']}")
        print(f"endpoint_count={result['endpoint_count']}")
        print(f"browser_check_count={result['browser_check_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

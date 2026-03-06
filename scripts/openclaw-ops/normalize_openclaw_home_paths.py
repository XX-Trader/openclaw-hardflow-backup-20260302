#!/usr/bin/env python3
"""Normalize legacy absolute home paths inside openclaw.json.

This script rewrites values like:
  /home/<user>/.openclaw/...  -> <OPENCLAW_HOME>/...
  /root/.openclaw/...         -> <OPENCLAW_HOME>/...
  /home/<user>/.claude/...    -> <CLAUDE_HOME>/...
  /root/.claude/...           -> <CLAUDE_HOME>/...

It is designed to make configuration portable across Linux users.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


OPENCLAW_PATTERN = re.compile(r"(/home/[^/\s\"']+|/root)/\.openclaw")
CLAUDE_PATTERN = re.compile(r"(/home/[^/\s\"']+|/root)/\.claude")


def to_json_pointer(parts: list[str]) -> str:
    if not parts:
        return "/"
    escaped = [p.replace("~", "~0").replace("/", "~1") for p in parts]
    return "/" + "/".join(escaped)


def normalize_string(value: str, openclaw_home: str, claude_home: str) -> tuple[str, bool]:
    updated = OPENCLAW_PATTERN.sub(openclaw_home, value)
    updated = CLAUDE_PATTERN.sub(claude_home, updated)
    return updated, updated != value


def rewrite_payload(node: Any, parts: list[str], openclaw_home: str, claude_home: str, changes: list[dict[str, str]]) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            out[key] = rewrite_payload(value, [*parts, str(key)], openclaw_home, claude_home, changes)
        return out
    if isinstance(node, list):
        out_list: list[Any] = []
        for idx, value in enumerate(node):
            out_list.append(rewrite_payload(value, [*parts, str(idx)], openclaw_home, claude_home, changes))
        return out_list
    if isinstance(node, str):
        new_text, changed = normalize_string(node, openclaw_home=openclaw_home, claude_home=claude_home)
        if changed:
            changes.append(
                {
                    "path": to_json_pointer(parts),
                    "before": node,
                    "after": new_text,
                }
            )
        return new_text
    return node


def backup_file(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_name(f"{path.name}.bak.homepath.{stamp}")
    bak.write_text(path.read_text(encoding="utf-8-sig"), encoding="utf-8")
    return bak


def main() -> int:
    home = Path(os.path.expanduser("~")).resolve()
    parser = argparse.ArgumentParser(description="Normalize openclaw.json home paths for current Linux user")
    parser.add_argument("--config", default=str(home / ".openclaw" / "openclaw.json"))
    parser.add_argument("--openclaw-home", default=os.environ.get("OPENCLAW_HOME", str(home / ".openclaw")))
    parser.add_argument("--claude-home", default=os.environ.get("CLAUDE_HOME", str(home / ".claude")))
    parser.add_argument("--allow-missing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    parser.add_argument("--max-preview", type=int, default=20)
    args = parser.parse_args()

    config_path = Path(str(args.config)).expanduser()
    openclaw_home = str(Path(str(args.openclaw_home)).expanduser().resolve())
    claude_home = str(Path(str(args.claude_home)).expanduser().resolve())

    if not config_path.exists():
        payload = {
            "ok": bool(args.allow_missing),
            "changed": False,
            "skipped": True,
            "reason": "config_not_found",
            "config": str(config_path),
            "openclaw_home": openclaw_home,
            "claude_home": claude_home,
        }
        if args.emit_json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"config={payload['config']}")
            print("status=skipped")
            print(f"reason={payload['reason']}")
        return 0 if args.allow_missing else 2

    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        payload = {
            "ok": False,
            "changed": False,
            "error": f"invalid_json:{exc}",
            "config": str(config_path),
        }
        if args.emit_json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(json.dumps(payload, ensure_ascii=False))
        return 2

    changes: list[dict[str, str]] = []
    updated = rewrite_payload(
        data,
        parts=[],
        openclaw_home=openclaw_home,
        claude_home=claude_home,
        changes=changes,
    )

    changed = len(changes) > 0
    backup = ""
    if changed and (not args.dry_run):
        backup = str(backup_file(config_path))
        config_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    payload = {
        "ok": True,
        "changed": changed,
        "dry_run": bool(args.dry_run),
        "config": str(config_path),
        "openclaw_home": openclaw_home,
        "claude_home": claude_home,
        "changes_count": len(changes),
        "backup": backup,
        "preview": changes[: max(1, int(args.max_preview))],
    }
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"config={payload['config']}")
        print(f"openclaw_home={payload['openclaw_home']}")
        print(f"claude_home={payload['claude_home']}")
        print(f"changed={str(changed).lower()}")
        print(f"changes_count={payload['changes_count']}")
        if backup:
            print(f"backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


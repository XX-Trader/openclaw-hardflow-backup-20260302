#!/usr/bin/env python3
"""Apply default zh-CN output policy to OpenClaw config and agent SOUL files."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


LANG_BLOCK = (
    "\n\n## 输出语言\n"
    "- 默认输出语言：中文（简体，zh-CN）。\n"
    "- 除非用户明确要求其他语言，否则所有回复必须使用中文（简体）。\n"
)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_language_policy(config: dict[str, Any]) -> bool:
    agents = config.setdefault("agents", {})
    if not isinstance(agents, dict):
        return False
    defaults = agents.setdefault("defaults", {})
    if not isinstance(defaults, dict):
        return False
    policy = defaults.setdefault("outputPolicy", {})
    if not isinstance(policy, dict):
        defaults["outputPolicy"] = {}
        policy = defaults["outputPolicy"]
    desired = {
        "defaultLanguage": "zh-CN",
        "defaultLanguageName": "中文（简体）",
        "requireChineseByDefault": True,
        "allowOverrideByUser": True,
    }
    changed = False
    for key, value in desired.items():
        if policy.get(key) != value:
            policy[key] = value
            changed = True
    return changed


def ensure_soul(path: Path) -> str:
    if path.exists():
        raw = path.read_text(encoding="utf-8-sig", errors="replace")
        if "默认输出语言" in raw:
            return "unchanged"
        path.write_text(raw.rstrip() + LANG_BLOCK + "\n", encoding="utf-8")
        return "updated"
    path.parent.mkdir(parents=True, exist_ok=True)
    agent_id = path.parent.parent.name
    content = (
        f"# {agent_id} profile\n"
        "\n"
        "## 输出语言\n"
        "- 默认输出语言：中文（简体，zh-CN）。\n"
        "- 除非用户明确要求其他语言，否则所有回复必须使用中文（简体）。\n"
    )
    path.write_text(content, encoding="utf-8")
    return "created"


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Apply default zh-CN output language policy")
    parser.add_argument("--config", default=str(home / ".openclaw/openclaw.json"))
    parser.add_argument("--agents-root", default=str(home / ".openclaw/agents"))
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser()
    agents_root = Path(args.agents_root).expanduser()

    config = read_json(config_path)
    config_changed = ensure_language_policy(config)
    agent_ids: list[str] = []
    agents = config.get("agents", {})
    if isinstance(agents, dict):
        for item in agents.get("list", []):
            if isinstance(item, dict):
                aid = str(item.get("id", "")).strip()
                if aid:
                    agent_ids.append(aid)

    if config_changed:
        write_json(config_path, config)

    soul_updated = 0
    soul_created = 0
    soul_unchanged = 0
    for aid in sorted(set(agent_ids)):
        status = ensure_soul(agents_root / aid / "agent" / "SOUL.md")
        if status == "updated":
            soul_updated += 1
        elif status == "created":
            soul_created += 1
        else:
            soul_unchanged += 1

    payload = {
        "ok": True,
        "host": os.uname().nodename if hasattr(os, "uname") else "",
        "config": str(config_path),
        "config_changed": config_changed,
        "agents_total": len(set(agent_ids)),
        "soul_updated": soul_updated,
        "soul_created": soul_created,
        "soul_unchanged": soul_unchanged,
    }
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"config_changed={str(config_changed).lower()}")
        print(f"agents_total={len(set(agent_ids))}")
        print(f"soul_updated={soul_updated}")
        print(f"soul_created={soul_created}")
        print(f"soul_unchanged={soul_unchanged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


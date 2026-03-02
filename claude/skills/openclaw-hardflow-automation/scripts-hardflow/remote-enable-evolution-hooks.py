#!/usr/bin/env python3
import json
from datetime import date
from pathlib import Path

HOOK_DIR = str(Path.home() / ".openclaw" / "hardflow-hooks")
CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"


def ensure_dict(parent, key):
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def ensure_list(parent, key):
    value = parent.get(key)
    if not isinstance(value, list):
        value = []
        parent[key] = value
    return value


def resolve_main_workspace(cfg):
    defaults = cfg.get("agents", {}).get("defaults", {})
    workspace = defaults.get("workspace")
    if isinstance(workspace, str) and workspace.strip():
        return Path(workspace.strip())
    return Path.home() / ".openclaw" / "workspace"


def ensure_memory_workspace(workspace):
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    memory_md = workspace / "MEMORY.md"
    if not memory_md.exists():
        memory_md.write_text(
            "# MEMORY.md\n\n"
            "## Purpose\n"
            "- Keep durable context for recurring tasks and operational decisions.\n\n"
            "## Policy\n"
            "- Prefer concise daily records in `memory/YYYY-MM-DD.md`.\n"
            "- Keep only actionable conclusions and verified outcomes.\n",
            encoding="utf-8",
        )

    today_file = memory_dir / f"{date.today().isoformat()}.md"
    if not today_file.exists():
        today_file.write_text(
            f"# {date.today().isoformat()} Memory Log\n\n"
            "- Initialized by hardflow evolution setup.\n",
            encoding="utf-8",
        )
    return memory_dir, memory_md, today_file


def main():
    if not CONFIG_PATH.exists():
        raise SystemExit(f"missing config: {CONFIG_PATH}")

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    hooks = ensure_dict(cfg, "hooks")
    internal = ensure_dict(hooks, "internal")
    internal["enabled"] = True

    load = ensure_dict(internal, "load")
    extra = ensure_list(load, "extraDirs")
    if HOOK_DIR not in extra:
        extra.append(HOOK_DIR)

    entries = ensure_dict(internal, "entries")
    capture = ensure_dict(entries, "hardflow-experience-capture")
    capture["enabled"] = True
    capture.setdefault("messages", 80)
    capture.setdefault("minMessages", 8)

    recall = ensure_dict(entries, "hardflow-experience-recall")
    recall["enabled"] = True
    recall.setdefault("topK", 5)

    evolve = ensure_dict(entries, "hardflow-experience-evolve")
    evolve["enabled"] = True

    workspace = resolve_main_workspace(cfg)
    memory_dir, memory_md, today_file = ensure_memory_workspace(workspace)

    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"updated {CONFIG_PATH}")
    print(f"hooks dir {HOOK_DIR}")
    print(f"workspace {workspace}")
    print(f"memory dir {memory_dir}")
    print(f"memory md {memory_md}")
    print(f"today file {today_file}")


if __name__ == "__main__":
    main()

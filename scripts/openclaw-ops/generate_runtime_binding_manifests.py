#!/usr/bin/env python3
"""Generate machine-readable runtime binding manifests from repository truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inspect_runtime_bindings import (
    ROOT,
    JsonValue,
    build_runtime_bindings_report,
    expect_dict,
    expect_list,
    extract_agent_list,
    load_json_object,
)


def write_json_if_changed(path: Path, payload: dict[str, JsonValue] | list[dict[str, JsonValue]]) -> bool:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True


def write_text_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def render_agent_index_md(items: list[dict[str, JsonValue]]) -> str:
    lines = ["# Agent Index", ""]
    for item in items:
        allow_agents = [str(value) for value in expect_list(item.get("allowAgents", []), "allowAgents")]
        lines.extend(
            [
                f"## {item['id']}",
                f"- name: {item['name']}",
                f"- default: {bool(item['default'])}",
                f"- workspace: {item['workspace']}",
                f"- agentDir: {item['agentDir']}",
                f"- model: {item['model']}",
                f"- allowAgentsCount: {len(allow_agents)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def build_agent_index_items(repo_root: Path) -> list[dict[str, JsonValue]]:
    openclaw_config = load_json_object(repo_root / "openclaw/openclaw.json")
    items: list[dict[str, JsonValue]] = []
    for agent in extract_agent_list(openclaw_config):
        subagents = expect_dict(agent.get("subagents", {}), "agent.subagents")
        items.append(
            {
                "id": str(agent.get("id", "")),
                "name": str(agent.get("name", "")),
                "default": bool(agent.get("default", False)),
                "workspace": str(agent.get("workspace", "")),
                "agentDir": agent.get("agentDir", None),
                "model": str(agent.get("model", "")),
                "allowAgents": [str(value) for value in expect_list(subagents.get("allowAgents", []), "allowAgents")],
            }
        )
    return items


def build_runtime_override_index(report: dict[str, JsonValue]) -> dict[str, list[dict[str, JsonValue]]]:
    override_index: dict[str, list[dict[str, JsonValue]]] = {}
    raw_conflicts = expect_list(report["runtime_skill_conflicts"], "runtime_skill_conflicts")
    for raw_conflict in raw_conflicts:
        conflict = expect_dict(raw_conflict, "runtime_skill_conflicts[]")
        affected_agents = [str(value) for value in expect_list(conflict["affected_agents"], "affected_agents")]
        for agent_id in affected_agents:
            override_index.setdefault(agent_id, []).append(
                {
                    "runtime_skill": str(conflict["runtime_skill"]),
                    "conflicts": [str(value) for value in expect_list(conflict["conflicts"], "conflicts")],
                }
            )
    return override_index


def build_agent_capability_manifest(report: dict[str, JsonValue]) -> dict[str, JsonValue]:
    hook_event_names = sorted(expect_dict(report["hook_events"], "hook_events"))
    override_index = build_runtime_override_index(report)
    manifest_agents: list[dict[str, JsonValue]] = []
    for raw_agent in expect_list(report["agents"], "agents"):
        agent = expect_dict(raw_agent, "agents[]")
        agent_id = str(agent["agent_id"])
        declared_skills = [str(value) for value in expect_list(agent["declared_skills"], "declared_skills")]
        missing_skills = [str(value) for value in expect_list(agent["missing_skills"], "missing_skills")]
        soul_skills = [str(value) for value in expect_list(agent["soul_skills"], "soul_skills")]
        manifest_agents.append(
            {
                "agent_id": agent_id,
                "name": str(agent["name"]),
                "default": bool(agent["default"]),
                "model": str(agent["model"]),
                "workspace": str(agent["workspace"]),
                "allow_agents": [str(value) for value in expect_list(agent["allow_agents"], "allow_agents")],
                "declared_skills": declared_skills,
                "missing_skills": missing_skills,
                "soul_skills": soul_skills,
                "runtime_skill_overrides": override_index.get(agent_id, []),
                "capability_mode": "role_only" if bool(agent["role_only"]) else "skill_backed",
                # Hooks are runtime-global, so every agent is affected by the enabled event set.
                "hook_events_affected": hook_event_names,
                "has_by_agent_doc": bool(agent["has_by_agent_doc"]),
                "has_soul_doc": bool(agent["has_soul_doc"]),
            }
        )
    return {
        "source_report": "scripts/openclaw-ops/inspect_runtime_bindings.py",
        "agents": manifest_agents,
    }


def build_hook_event_matrix(report: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "hooks": expect_list(report["hooks"], "hooks"),
        "events": expect_dict(report["hook_events"], "hook_events"),
    }


def generate_runtime_binding_manifests(repo_root: Path = ROOT) -> list[str]:
    report = build_runtime_bindings_report(repo_root)
    changed_files: list[str] = []
    agent_manifest = build_agent_capability_manifest(report)
    hook_matrix = build_hook_event_matrix(report)
    agent_index_items = build_agent_index_items(repo_root)
    outputs: list[tuple[Path, dict[str, JsonValue] | list[dict[str, JsonValue]]]] = [
        (repo_root / "agents/agent_capability_manifest.json", agent_manifest),
        (repo_root / "hooks/index/hook_event_matrix.json", hook_matrix),
        (repo_root / "agents/agent_index.json", agent_index_items),
    ]
    for path, payload in outputs:
        if write_json_if_changed(path, payload):
            changed_files.append(path.relative_to(repo_root).as_posix())
    agent_index_md_path = repo_root / "agents/agent_index.md"
    agent_index_md = render_agent_index_md(agent_index_items)
    if write_text_if_changed(agent_index_md_path, agent_index_md):
        changed_files.append(agent_index_md_path.relative_to(repo_root).as_posix())
    return changed_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Repository root that contains openclaw/, agents/, hooks/, and cron/.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    changed_files = generate_runtime_binding_manifests(args.repo_root.resolve())
    if not changed_files:
        print("No manifest files changed.")
        return 0
    for path in changed_files:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

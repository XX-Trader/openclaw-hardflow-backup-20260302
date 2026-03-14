#!/usr/bin/env python3
"""Inspect runtime agent, skill, hook, and cron bindings without mutations."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

ROOT = Path(__file__).resolve().parents[2]
TZ = timezone(timedelta(hours=8))
BUILTIN_HOOKS = {"boot-md", "command-logger", "session-memory"}
SKILL_STATUS_RE = re.compile(r"^- ([A-Za-z0-9_.-]+) \((present|missing)\)$")
CRON_BINDING_RE = re.compile(
    r"^- (?P<job_id>[^|]+?) \| (?P<job_name>[^|]+?) \| "
    r"agent=(?P<agent_id>[^|]+?) \| exists=(?P<exists>[^|]+?) \| "
    r"schedule=(?P<schedule>.+)$"
)


@dataclass(frozen=True)
class AgentMatrixSkills:
    declared_skills: list[str]
    missing_skills: list[str]


@dataclass(frozen=True)
class HookDoc:
    name: str
    events: list[str]


@dataclass(frozen=True)
class CronBinding:
    job_id: str
    job_name: str
    agent_id: str
    exists_in_mapping: bool
    schedule: str


@dataclass(frozen=True)
class RuntimeSkillRequirement:
    name: str
    conflicts: list[str]


def expect_dict(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def expect_list(value: JsonValue, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def load_json_object(path: Path) -> dict[str, JsonValue]:
    return expect_dict(json.loads(path.read_text(encoding="utf-8")), str(path))


def ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def normalize_skill_block(raw_value: str) -> list[str]:
    skills = [part.strip() for part in raw_value.split(",")]
    return ordered_unique([skill for skill in skills if skill])


def parse_agent_matrix_skills(path: Path) -> AgentMatrixSkills:
    declared_skills: list[str] = []
    missing_skills: list[str] = []
    in_skills_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "## Skills":
            in_skills_section = True
            continue
        if not in_skills_section:
            continue
        if stripped.startswith("## "):
            break
        if stripped == "- (none declared)":
            return AgentMatrixSkills(declared_skills=[], missing_skills=[])
        match = SKILL_STATUS_RE.match(stripped)
        if match is None:
            continue
        skill_name = match.group(1)
        declared_skills.append(skill_name)
        if match.group(2) == "missing":
            missing_skills.append(skill_name)
    return AgentMatrixSkills(
        declared_skills=ordered_unique(declared_skills),
        missing_skills=ordered_unique(missing_skills),
    )


def parse_soul_skills(path: Path) -> list[str]:
    skill_lines: list[str] = []
    capture_block = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped in {"## 技能主线", "## 扩展技能"}:
            capture_block = True
            continue
        if capture_block and stripped.startswith("## "):
            capture_block = False
        if not capture_block or "`" not in stripped:
            continue
        parts = re.findall(r"`([^`]+)`", stripped)
        for part in parts:
            skill_lines.extend(normalize_skill_block(part))
    return ordered_unique(skill_lines)


def parse_hook_doc(path: Path) -> HookDoc:
    frontmatter: list[str] = []
    in_frontmatter = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "---" and not in_frontmatter:
            in_frontmatter = True
            continue
        if stripped == "---" and in_frontmatter:
            break
        if in_frontmatter:
            frontmatter.append(stripped)
    name = path.parent.name
    events: list[str] = []
    for line in frontmatter:
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
            continue
        if not line.startswith("metadata:"):
            continue
        metadata_raw = line.split(":", 1)[1].strip()
        metadata = expect_dict(json.loads(metadata_raw), f"{path}:metadata")
        openclaw = expect_dict(metadata.get("openclaw", {}), f"{path}:metadata.openclaw")
        raw_events = expect_list(openclaw.get("events", []), f"{path}:metadata.openclaw.events")
        events = [str(item) for item in raw_events]
    return HookDoc(name=name, events=ordered_unique(events))


def parse_cron_bindings(path: Path) -> list[CronBinding]:
    bindings: list[CronBinding] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = CRON_BINDING_RE.match(line.strip())
        if match is None:
            continue
        bindings.append(
            CronBinding(
                job_id=match.group("job_id").strip(),
                job_name=match.group("job_name").strip(),
                agent_id=match.group("agent_id").strip(),
                exists_in_mapping=match.group("exists").strip().lower() == "true",
                schedule=match.group("schedule").strip(),
            )
        )
    return bindings


def parse_agent_index_json_defaults(path: Path) -> dict[str, bool]:
    if not path.exists():
        return {}
    defaults: dict[str, bool] = {}
    for item in expect_list(json.loads(path.read_text(encoding="utf-8")), str(path)):
        agent = expect_dict(item, f"{path}:item")
        agent_id = str(agent.get("id", ""))
        defaults[agent_id] = bool(agent.get("default", False))
    return defaults


def parse_agent_index_md_defaults(path: Path) -> dict[str, bool]:
    if not path.exists():
        return {}
    defaults: dict[str, bool] = {}
    current_agent_id = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current_agent_id = stripped[3:].strip()
            defaults.setdefault(current_agent_id, False)
            continue
        if current_agent_id and stripped.startswith("- default:"):
            raw_value = stripped.split(":", 1)[1].strip().lower()
            defaults[current_agent_id] = raw_value == "true"
    return defaults


def parse_runtime_required_skills(path: Path) -> list[RuntimeSkillRequirement]:
    if not path.exists():
        return []
    config = load_json_object(path)
    requirements: list[RuntimeSkillRequirement] = []
    for item in expect_list(config.get("skills", []), f"{path}:skills"):
        entry = expect_dict(item, f"{path}:skills:item")
        skill_name = str(entry.get("name", ""))
        conflicts = [str(value) for value in expect_list(entry.get("conflicts", []), f"{path}:conflicts")]
        requirements.append(
            RuntimeSkillRequirement(
                name=skill_name,
                conflicts=ordered_unique(conflicts),
            )
        )
    return requirements


def extract_agent_list(config: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    agents = expect_dict(config.get("agents", {}), "openclaw.agents")
    raw_agent_list = expect_list(agents.get("list", []), "openclaw.agents.list")
    return [expect_dict(item, "openclaw.agents.list[]") for item in raw_agent_list]


def extract_allow_agents(agent_config: dict[str, JsonValue]) -> list[str]:
    subagents = expect_dict(agent_config.get("subagents", {}), "agent.subagents")
    allow_agents = expect_list(subagents.get("allowAgents", []), "agent.subagents.allowAgents")
    return ordered_unique([str(item) for item in allow_agents])


def collect_hook_docs(repo_root: Path) -> dict[str, HookDoc]:
    docs: dict[str, HookDoc] = {}
    for path in sorted((repo_root / "hooks").glob("*/HOOK.md")):
        hook_doc = parse_hook_doc(path)
        docs[hook_doc.name] = hook_doc
    return docs


def collect_agent_matrix_docs(repo_root: Path) -> dict[str, AgentMatrixSkills]:
    docs: dict[str, AgentMatrixSkills] = {}
    for path in sorted((repo_root / "skills/by_agent").glob("*.md")):
        docs[path.stem] = parse_agent_matrix_skills(path)
    return docs


def collect_agent_soul_docs(repo_root: Path) -> dict[str, list[str]]:
    docs: dict[str, list[str]] = {}
    for path in sorted((repo_root / "agents").glob("*/SOUL.md")):
        docs[path.parent.name] = parse_soul_skills(path)
    return docs


def build_agent_reports(
    agent_configs: list[dict[str, JsonValue]],
    matrix_docs: dict[str, AgentMatrixSkills],
    soul_docs: dict[str, list[str]],
) -> list[dict[str, JsonValue]]:
    reports: list[dict[str, JsonValue]] = []
    for agent_config in agent_configs:
        agent_id = str(agent_config.get("id", ""))
        matrix_doc = matrix_docs.get(agent_id, AgentMatrixSkills([], []))
        soul_skills = soul_docs.get(agent_id, [])
        declared_skills = matrix_doc.declared_skills
        reports.append(
            {
                "agent_id": agent_id,
                "name": str(agent_config.get("name", "")),
                "default": bool(agent_config.get("default", False)),
                "model": str(agent_config.get("model", "")),
                "workspace": str(agent_config.get("workspace", "")),
                "allow_agents": extract_allow_agents(agent_config),
                "declared_skills": declared_skills,
                "missing_skills": matrix_doc.missing_skills,
                "soul_skills": soul_skills,
                "matrix_only_skills": sorted(set(declared_skills) - set(soul_skills)),
                "soul_only_skills": sorted(set(soul_skills) - set(declared_skills)),
                "has_by_agent_doc": agent_id in matrix_docs,
                "has_soul_doc": agent_id in soul_docs,
                "role_only": not declared_skills and not soul_skills,
            }
        )
    return reports


def build_runtime_skill_conflicts(
    requirements: list[RuntimeSkillRequirement],
    agent_reports: list[dict[str, JsonValue]],
) -> list[dict[str, JsonValue]]:
    conflicts: list[dict[str, JsonValue]] = []
    for requirement in requirements:
        affected_agents: list[str] = []
        for agent in agent_reports:
            declared_skills = [str(item) for item in expect_list(agent["declared_skills"], "agent.declared_skills")]
            if set(declared_skills).intersection(requirement.conflicts):
                affected_agents.append(str(agent["agent_id"]))
        conflicts.append(
            {
                "runtime_skill": requirement.name,
                "conflicts": requirement.conflicts,
                "affected_agents": ordered_unique(affected_agents),
            }
        )
    return conflicts


def build_hook_reports(
    hook_entries: dict[str, JsonValue],
    hook_docs: dict[str, HookDoc],
) -> tuple[list[dict[str, JsonValue]], dict[str, list[str]]]:
    hooks: list[dict[str, JsonValue]] = []
    event_map: dict[str, list[str]] = {}
    for hook_name in sorted(hook_entries):
        hook_entry = expect_dict(hook_entries[hook_name], f"hooks.internal.entries.{hook_name}")
        hook_doc = hook_docs.get(hook_name, HookDoc(name=hook_name, events=[]))
        hook_events = ordered_unique(hook_doc.events)
        hooks.append(
            {
                "name": hook_name,
                "enabled": bool(hook_entry.get("enabled", False)),
                "classification": "builtin" if hook_name in BUILTIN_HOOKS else "custom",
                "events": hook_events,
                "has_doc": hook_name in hook_docs,
            }
        )
        for event_name in hook_events:
            event_map.setdefault(event_name, []).append(hook_name)
    normalized_event_map = {key: value for key, value in sorted(event_map.items())}
    return hooks, normalized_event_map


def build_index_drift(
    agent_reports: list[dict[str, JsonValue]],
    matrix_docs: dict[str, AgentMatrixSkills],
    soul_docs: dict[str, list[str]],
    hook_docs: dict[str, HookDoc],
    hook_entries: dict[str, JsonValue],
    cron_bindings: list[CronBinding],
    repo_root: Path,
) -> dict[str, JsonValue]:
    agent_ids = [str(agent["agent_id"]) for agent in agent_reports]
    openclaw_defaults = sorted([agent_id for agent_id, agent in zip(agent_ids, agent_reports) if bool(agent["default"])])
    index_json_defaults = sorted(
        [agent_id for agent_id, is_default in parse_agent_index_json_defaults(repo_root / "agents/agent_index.json").items() if is_default]
    )
    index_md_defaults = sorted(
        [agent_id for agent_id, is_default in parse_agent_index_md_defaults(repo_root / "agents/agent_index.md").items() if is_default]
    )
    return {
        "default_agent": {
            "openclaw": openclaw_defaults,
            "agent_index_json": index_json_defaults,
            "agent_index_md": index_md_defaults,
            "matches": openclaw_defaults == index_json_defaults == index_md_defaults,
        },
        "missing_by_agent_docs": sorted(set(agent_ids) - set(matrix_docs)),
        "extra_by_agent_docs": sorted(set(matrix_docs) - set(agent_ids)),
        "missing_soul_docs": sorted(set(agent_ids) - set(soul_docs)),
        "extra_soul_docs": sorted(set(soul_docs) - set(agent_ids)),
        "custom_hooks_missing_docs": sorted(
            hook_name for hook_name in hook_entries if hook_name not in BUILTIN_HOOKS and hook_name not in hook_docs
        ),
        "unknown_cron_agents": sorted(
            {binding.agent_id for binding in cron_bindings if binding.agent_id not in set(agent_ids)}
        ),
    }


def build_runtime_bindings_report(repo_root: Path = ROOT) -> dict[str, JsonValue]:
    openclaw_config = load_json_object(repo_root / "openclaw/openclaw.json")
    agent_configs = extract_agent_list(openclaw_config)
    matrix_docs = collect_agent_matrix_docs(repo_root)
    soul_docs = collect_agent_soul_docs(repo_root)
    hook_docs = collect_hook_docs(repo_root)
    runtime_requirements = parse_runtime_required_skills(
        repo_root / "scripts/openclaw-ops/runtime-required-skills.json"
    )
    hook_root = expect_dict(openclaw_config.get("hooks", {}), "openclaw.hooks")
    hook_internal = expect_dict(hook_root.get("internal", {}), "openclaw.hooks.internal")
    hook_entries = expect_dict(hook_internal.get("entries", {}), "openclaw.hooks.internal.entries")
    cron_bindings = parse_cron_bindings(repo_root / "cron/jobs_agent_mapping.md")
    agent_reports = build_agent_reports(agent_configs, matrix_docs, soul_docs)
    hooks, hook_events = build_hook_reports(hook_entries, hook_docs)
    declared_skills = sorted(
        set(skill for report in agent_reports for skill in expect_list(report["declared_skills"], "agent.declared_skills"))
    )
    missing_skills = sorted(
        set(skill for report in agent_reports for skill in expect_list(report["missing_skills"], "agent.missing_skills"))
    )
    agent_id_set = {str(report["agent_id"]) for report in agent_reports}
    cron_binding_reports = [
        {
            "job_id": binding.job_id,
            "job_name": binding.job_name,
            "agent_id": binding.agent_id,
            "declared_exists": binding.exists_in_mapping,
            "agent_exists": binding.agent_id in agent_id_set,
            "schedule": binding.schedule,
        }
        for binding in cron_bindings
    ]
    report: dict[str, JsonValue] = {
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "summary": {
            "agent_count": len(agent_reports),
            "declared_skill_count": len(declared_skills),
            "missing_skill_count": len(missing_skills),
            "hook_count": len(hooks),
            "cron_binding_count": len(cron_binding_reports),
        },
        "agents": agent_reports,
        "declared_skills": [str(skill) for skill in declared_skills],
        "missing_skills": [str(skill) for skill in missing_skills],
        "runtime_required_skills": [
            {
                "name": requirement.name,
                "conflicts": requirement.conflicts,
            }
            for requirement in runtime_requirements
        ],
        "runtime_skill_conflicts": build_runtime_skill_conflicts(runtime_requirements, agent_reports),
        "hooks": hooks,
        "hook_events": hook_events,
        "cron_agent_bindings": cron_binding_reports,
        "index_drift": build_index_drift(
            agent_reports=agent_reports,
            matrix_docs=matrix_docs,
            soul_docs=soul_docs,
            hook_docs=hook_docs,
            hook_entries=hook_entries,
            cron_bindings=cron_bindings,
            repo_root=repo_root,
        ),
    }
    return report


def join_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "(none)"


def render_human_summary(report: dict[str, JsonValue]) -> str:
    summary = expect_dict(report["summary"], "report.summary")
    index_drift = expect_dict(report["index_drift"], "report.index_drift")
    default_agent = expect_dict(index_drift["default_agent"], "report.index_drift.default_agent")
    missing_skills = [str(item) for item in expect_list(report["missing_skills"], "report.missing_skills")]
    unknown_cron_agents = [str(item) for item in expect_list(index_drift["unknown_cron_agents"], "report.index_drift.unknown_cron_agents")]
    missing_by_agent_docs = [
        str(item) for item in expect_list(index_drift["missing_by_agent_docs"], "report.index_drift.missing_by_agent_docs")
    ]
    runtime_conflicts = [
        expect_dict(item, "report.runtime_skill_conflicts[]")
        for item in expect_list(report["runtime_skill_conflicts"], "report.runtime_skill_conflicts")
    ]
    conflict_lines = [
        f"{str(item['runtime_skill'])} <= {join_or_none([str(value) for value in expect_list(item['conflicts'], 'conflicts')])}"
        f" | agents={join_or_none([str(value) for value in expect_list(item['affected_agents'], 'affected_agents')])}"
        for item in runtime_conflicts
    ]
    lines = [
        "Runtime Binding Report",
        f"- generated_at: {report['generated_at']}",
        f"- agents: {summary['agent_count']}",
        f"- declared_skills: {summary['declared_skill_count']}",
        f"- missing_skills: {join_or_none(missing_skills)}",
        f"- hooks: {summary['hook_count']}",
        f"- cron_bindings: {summary['cron_binding_count']}",
        "- default_agent:",
        f"  openclaw={join_or_none([str(item) for item in expect_list(default_agent['openclaw'], 'default_agent.openclaw')])}"
        f" | agent_index_json={join_or_none([str(item) for item in expect_list(default_agent['agent_index_json'], 'default_agent.agent_index_json')])}"
        f" | agent_index_md={join_or_none([str(item) for item in expect_list(default_agent['agent_index_md'], 'default_agent.agent_index_md')])}",
        f"- missing_by_agent_docs: {join_or_none(missing_by_agent_docs)}",
        f"- unknown_cron_agents: {join_or_none(unknown_cron_agents)}",
        f"- runtime_skill_conflicts: {join_or_none(conflict_lines)}",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=ROOT,
        help="Repository root that contains openclaw/, agents/, hooks/, and cron/.",
    )
    parser.add_argument(
        "--emit-json",
        action="store_true",
        help="Print the full machine-readable report as JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_runtime_bindings_report(args.repo_root.resolve())
    if args.emit_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(render_human_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

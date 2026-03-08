#!/usr/bin/env python3
"""One-command model tier switcher for OpenClaw workflow files."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
POLICY_DIR = SCRIPT_DIR / "policy"
if str(POLICY_DIR) not in sys.path:
    sys.path.insert(0, str(POLICY_DIR))

from io_write_gateway import atomic_write_text, write_json_atomic

REPO_ROOT = SCRIPT_DIR.parent.parent
PROFILE_FILE = SCRIPT_DIR / "model_tier_profiles.json"
BACKUP_ROOT = REPO_ROOT / ".tmp" / "model-switch-backups"
PROFILE_SNAPSHOT_ROOT = REPO_ROOT / ".tmp" / "model-switch-profiles"

MODEL_ALIAS_MAP: dict[str, str] = {
    "openai-codex/gpt-5.4": "codex",
    "openai-codex/gpt-5.3-codex-spark": "codexspark",
    "kimicode/Doubao-Seed-2.0-Code": "doubao",
    "glmcode/glm-5": "glm",
    "glmcode/glm-4.7": "glm47",
}


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def normalize_alias(value: str) -> str:
    return re.sub(r"[\s_\-./]+", "", str(value or "").strip().lower())


def ordered_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in values:
        model = str(item).strip()
        if not model or model in seen:
            continue
        out.append(model)
        seen.add(model)
    return out


def read_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8-sig")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"JSON object required: {path}")
    return obj


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_json_atomic(
        path,
        payload,
        ensure_ascii=False,
        indent=2,
        file_mode=0o640,
        dir_mode=0o750,
    )


def load_profiles(path: Path) -> dict[str, Any]:
    data = read_json(path)
    tiers = data.get("tiers")
    if not isinstance(tiers, dict) or not tiers:
        raise ValueError("model_tier_profiles.json missing non-empty tiers")
    return data


def build_tier_alias_index(profiles: dict[str, Any]) -> dict[str, str]:
    tiers = profiles["tiers"]
    alias_to_tier: dict[str, str] = {}
    for tier_key, conf in tiers.items():
        alias_to_tier[normalize_alias(tier_key)] = tier_key
        if not isinstance(conf, dict):
            continue
        for alias in conf.get("aliases", []):
            norm = normalize_alias(str(alias))
            if norm:
                alias_to_tier[norm] = tier_key
    return alias_to_tier


def resolve_tier(raw: str, profiles: dict[str, Any]) -> str:
    tiers = profiles["tiers"]
    alias_index = build_tier_alias_index(profiles)
    default_tier = str(profiles.get("default_tier", "high")).strip().lower()

    text = str(raw or "").strip()
    if not text:
        return default_tier if default_tier in tiers else "high"

    normalized = normalize_alias(text)
    if normalized in alias_index:
        return alias_index[normalized]

    fuzzy_rules = [
        ("top", ("顶级", "最高", "codex", "xhigh")),
        ("high_doubao", ("豆包", "doubao", "chatdoubao", "highdoubao")),
        ("high", ("高级", "high", "advanced")),
        ("medium", ("中级", "glm5", "glm-5", "mid", "medium")),
        ("low", ("低级", "glm47", "glm-4.7", "lite", "low")),
    ]
    lowered = text.lower()
    for tier, keys in fuzzy_rules:
        if tier not in tiers:
            continue
        if any(k in text or k in lowered for k in keys):
            return tier

    valid = ", ".join(sorted(tiers.keys()))
    raise ValueError(f"无法识别档位: {text}. 可选: {valid}")


def ensure_profile(profile: dict[str, Any], tier: str) -> dict[str, Any]:
    primary = str(profile.get("primary_model", "")).strip()
    if not primary:
        raise ValueError(f"档位 {tier} 缺少 primary_model")
    fallbacks_raw = profile.get("fallback_models", [])
    if not isinstance(fallbacks_raw, list):
        raise ValueError(f"档位 {tier} 的 fallback_models 必须是数组")
    fallbacks = ordered_unique([str(x).strip() for x in fallbacks_raw if str(x).strip()])
    agent_overrides_raw = profile.get("agent_model_overrides", {})
    if not isinstance(agent_overrides_raw, dict):
        raise ValueError(f"档位 {tier} 的 agent_model_overrides 必须是对象")
    agent_model_overrides: dict[str, str] = {}
    for agent_id, model_id in agent_overrides_raw.items():
        agent = str(agent_id).strip()
        model = str(model_id).strip()
        if not agent or not model:
            continue
        agent_model_overrides[agent] = model
    thinking_overrides_raw = profile.get("model_thinking_overrides", {})
    if not isinstance(thinking_overrides_raw, dict):
        raise ValueError(f"档位 {tier} 的 model_thinking_overrides 必须是对象")
    model_thinking_overrides: dict[str, str] = {}
    for model_id, thinking in thinking_overrides_raw.items():
        model = str(model_id).strip()
        level = str(thinking).strip().lower()
        if not model or not level:
            continue
        model_thinking_overrides[model] = level
    thinking_default = str(profile.get("thinking_default", "")).strip() or "high"
    return {
        "name": str(profile.get("name", tier)).strip() or tier,
        "primary_model": primary,
        "fallback_models": fallbacks,
        "agent_model_overrides": agent_model_overrides,
        "model_thinking_overrides": model_thinking_overrides,
        "thinking_default": thinking_default,
    }


def build_default_model_aliases(
    chain: list[str],
    existing: dict[str, Any],
    model_thinking_overrides: dict[str, str],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for model_id in chain:
        alias = MODEL_ALIAS_MAP.get(model_id) or model_id.split("/")[-1]
        payload: dict[str, Any] = {"alias": alias}
        thinking = str(model_thinking_overrides.get(model_id, "")).strip().lower()
        if thinking:
            payload["params"] = {"thinking": thinking}
        result[model_id] = payload

    for model_id, meta in existing.items():
        if model_id in result:
            continue
        if isinstance(meta, dict):
            result[model_id] = meta
    return result


def apply_openclaw_config(data: dict[str, Any], profile: dict[str, Any]) -> tuple[bool, list[str]]:
    changed = False
    primary = profile["primary_model"]
    fallbacks = profile["fallback_models"]
    agent_model_overrides = profile["agent_model_overrides"]
    model_thinking_overrides = profile["model_thinking_overrides"]
    thinking_default = profile["thinking_default"]

    agents_obj = data.setdefault("agents", {})
    if not isinstance(agents_obj, dict):
        raise ValueError("openclaw.json: agents 必须是对象")

    defaults = agents_obj.setdefault("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("openclaw.json: agents.defaults 必须是对象")

    model_obj = defaults.get("model")
    if not isinstance(model_obj, dict):
        model_obj = {}
    expected_model_obj = {"primary": primary, "fallbacks": list(fallbacks)}
    if model_obj != expected_model_obj:
        defaults["model"] = expected_model_obj
        changed = True

    existing_models = defaults.get("models", {})
    if not isinstance(existing_models, dict):
        existing_models = {}
    chain = ordered_unique([primary, *fallbacks, *agent_model_overrides.values(), *model_thinking_overrides.keys()])
    expected_alias_map = build_default_model_aliases(
        chain=chain,
        existing=existing_models,
        model_thinking_overrides=model_thinking_overrides,
    )
    if defaults.get("models") != expected_alias_map:
        defaults["models"] = expected_alias_map
        changed = True

    if defaults.get("thinkingDefault") != thinking_default:
        defaults["thinkingDefault"] = thinking_default
        changed = True

    managed_agent_ids: list[str] = []
    agent_list = agents_obj.get("list", [])
    if isinstance(agent_list, list):
        for item in agent_list:
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("id", "")).strip()
            if not agent_id:
                continue
            managed_agent_ids.append(agent_id)
            target_model = agent_model_overrides.get(agent_id, primary)
            if item.get("model") != target_model:
                item["model"] = target_model
                changed = True

    return changed, managed_agent_ids


def apply_agent_index_json(
    data: list[dict[str, Any]],
    primary_model: str,
    managed_agent_ids: set[str],
    agent_model_overrides: dict[str, str],
) -> tuple[bool, list[dict[str, Any]]]:
    changed = False
    if not isinstance(data, list):
        raise ValueError("agents/agent_index.json 必须是数组")

    for item in data:
        if not isinstance(item, dict):
            continue
        agent_id = str(item.get("id", "")).strip()
        if managed_agent_ids and agent_id not in managed_agent_ids:
            continue
        target_model = agent_model_overrides.get(agent_id, primary_model)
        if item.get("model") != target_model:
            item["model"] = target_model
            changed = True

    return changed, data


def render_agent_index_md(items: list[dict[str, Any]]) -> str:
    lines = ["# Agent Index", ""]
    for item in items:
        if not isinstance(item, dict):
            continue
        agent_id = str(item.get("id", "")).strip()
        if not agent_id:
            continue
        allow_agents = item.get("allowAgents", [])
        if not isinstance(allow_agents, list):
            allow_agents = []
        lines.extend(
            [
                f"## {agent_id}",
                f"- name: {item.get('name', '')}",
                f"- default: {bool(item.get('default', False))}",
                f"- workspace: {item.get('workspace', '')}",
                f"- agentDir: {item.get('agentDir', None)}",
                f"- model: {item.get('model', '')}",
                f"- allowAgentsCount: {len(allow_agents)}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def apply_policy_config(data: dict[str, Any], profile: dict[str, Any]) -> bool:
    changed = False
    primary = profile["primary_model"]
    fallbacks = profile["fallback_models"]
    agent_model_overrides = profile["agent_model_overrides"]
    model_thinking_overrides = profile["model_thinking_overrides"]
    allowed = ordered_unique([primary, *fallbacks, *agent_model_overrides.values()])

    if data.get("primary_model") != primary:
        data["primary_model"] = primary
        changed = True
    if data.get("fallback_models") != fallbacks:
        data["fallback_models"] = list(fallbacks)
        changed = True
    if data.get("allowed_models") != allowed:
        data["allowed_models"] = allowed
        changed = True
    if data.get("agent_model_overrides") != agent_model_overrides:
        data["agent_model_overrides"] = dict(agent_model_overrides)
        changed = True
    if data.get("model_thinking_overrides") != model_thinking_overrides:
        data["model_thinking_overrides"] = dict(model_thinking_overrides)
        changed = True
    return changed


def apply_hardflow_policy_model(text: str, primary_model: str) -> tuple[bool, str]:
    pattern = re.compile(r'^(POLICY_MODEL="\$\{POLICY_MODEL:-)([^}]+)(\}"\s*)$', re.MULTILINE)
    updated, count = pattern.subn(lambda m: f"{m.group(1)}{primary_model}{m.group(3)}", text, count=1)
    if count == 0:
        raise ValueError("scripts/hardflow/hardflow-run.sh 未找到 POLICY_MODEL 默认值")
    return (updated != text), updated


def backup_files(paths: list[Path], backup_dir: Path, repo_root: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for file_path in paths:
        if not file_path.exists():
            continue
        rel = file_path.relative_to(repo_root)
        dst = backup_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dst)


def write_backup_meta(
    backup_dir: Path,
    tier_key: str,
    profile: dict[str, Any],
    changed_files: list[str],
    dry_run: bool,
    requested_text: str,
) -> None:
    payload = {
        "schema_version": "2026-03-03",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tier": tier_key,
        "requested_text": requested_text,
        "profile": profile,
        "dry_run": dry_run,
        "changed_files": changed_files,
    }
    write_json(backup_dir / "metadata.json", payload)


def write_profile_snapshot(tier_key: str, profile: dict[str, Any]) -> Path:
    PROFILE_SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    out = PROFILE_SNAPSHOT_ROOT / f"{stamp()}_{tier_key}.json"
    write_json(
        out,
        {
            "schema_version": "2026-03-03",
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "tier": tier_key,
            "profile": profile,
        },
    )
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="一键切换 OpenClaw 模型档位（含自动备份）")
    parser.add_argument("request", nargs="?", default="", help="档位或一句话，例如: 顶级 / 高级 / 切换顶级模型")
    parser.add_argument("--tier", default="", help="明确指定档位: top/high/medium/low")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")
    parser.add_argument("--list-tiers", action="store_true", help="列出可用档位")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="仓库根目录")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    profiles = load_profiles(PROFILE_FILE)
    tiers = profiles["tiers"]

    if args.list_tiers:
        print("available_tiers:")
        for key, conf in tiers.items():
            conf_obj = ensure_profile(conf if isinstance(conf, dict) else {}, key)
            fallbacks = ",".join(conf_obj["fallback_models"]) if conf_obj["fallback_models"] else "-"
            print(f"- {key} ({conf_obj['name']}): primary={conf_obj['primary_model']} fallbacks={fallbacks}")
        return 0

    requested_text = args.tier.strip() or args.request.strip()
    tier_key = resolve_tier(requested_text, profiles)
    profile = ensure_profile(tiers[tier_key], tier_key)

    openclaw_path = repo_root / "openclaw" / "openclaw.json"
    agent_index_json_path = repo_root / "agents" / "agent_index.json"
    agent_index_md_path = repo_root / "agents" / "agent_index.md"
    policy_config_path = repo_root / "scripts" / "openclaw-ops" / "policy" / "policy-config.json"
    hardflow_path = repo_root / "scripts" / "hardflow" / "hardflow-run.sh"

    required_files = [openclaw_path, agent_index_json_path, policy_config_path, hardflow_path]
    missing = [str(p) for p in required_files if not p.exists()]
    if missing:
        raise SystemExit("missing required files:\n" + "\n".join(missing))

    openclaw_data = read_json(openclaw_path)
    changed_openclaw, managed_agent_ids = apply_openclaw_config(openclaw_data, profile)
    managed_id_set = set(managed_agent_ids)

    agent_index_data_raw = json.loads(agent_index_json_path.read_text(encoding="utf-8-sig"))
    changed_index_json, agent_index_items = apply_agent_index_json(
        data=agent_index_data_raw,
        primary_model=profile["primary_model"],
        managed_agent_ids=managed_id_set,
        agent_model_overrides=profile["agent_model_overrides"],
    )
    rendered_agent_index_md = render_agent_index_md(agent_index_items)
    old_agent_index_md = agent_index_md_path.read_text(encoding="utf-8-sig") if agent_index_md_path.exists() else ""
    changed_index_md = rendered_agent_index_md != old_agent_index_md

    policy_config_data = read_json(policy_config_path)
    changed_policy = apply_policy_config(policy_config_data, profile)

    hardflow_text = hardflow_path.read_text(encoding="utf-8-sig")
    changed_hardflow, updated_hardflow_text = apply_hardflow_policy_model(
        text=hardflow_text,
        primary_model=profile["primary_model"],
    )

    changed_files: list[Path] = []
    if changed_openclaw:
        changed_files.append(openclaw_path)
    if changed_index_json:
        changed_files.append(agent_index_json_path)
    if changed_index_md:
        changed_files.append(agent_index_md_path)
    if changed_policy:
        changed_files.append(policy_config_path)
    if changed_hardflow:
        changed_files.append(hardflow_path)

    changed_rel = [str(p.relative_to(repo_root)).replace("\\", "/") for p in changed_files]
    print(f"tier={tier_key}")
    print(f"primary={profile['primary_model']}")
    print(f"fallbacks={','.join(profile['fallback_models']) if profile['fallback_models'] else '-'}")
    print(f"agent_overrides={len(profile['agent_model_overrides'])}")
    print(f"thinking_default={profile['thinking_default']}")
    print(f"managed_agents={len(managed_id_set)}")
    print(f"dry_run={str(bool(args.dry_run)).lower()}")
    if changed_rel:
        print("changed_files=" + ",".join(changed_rel))
    else:
        print("changed_files=-")

    if args.dry_run:
        return 0

    backup_dir = BACKUP_ROOT / f"{stamp()}_{tier_key}"
    backup_files(
        paths=[openclaw_path, agent_index_json_path, agent_index_md_path, policy_config_path, hardflow_path],
        backup_dir=backup_dir,
        repo_root=repo_root,
    )
    write_backup_meta(
        backup_dir=backup_dir,
        tier_key=tier_key,
        profile=profile,
        changed_files=changed_rel,
        dry_run=False,
        requested_text=requested_text,
    )

    if changed_openclaw:
        write_json(openclaw_path, openclaw_data)
    if changed_index_json:
        write_json_atomic(
            agent_index_json_path,
            agent_index_items,
            ensure_ascii=False,
            indent=2,
            file_mode=0o640,
            dir_mode=0o750,
        )
    if changed_index_md:
        atomic_write_text(
            agent_index_md_path,
            rendered_agent_index_md,
            encoding="utf-8",
            file_mode=0o640,
            dir_mode=0o750,
        )
    if changed_policy:
        write_json(policy_config_path, policy_config_data)
    if changed_hardflow:
        atomic_write_text(
            hardflow_path,
            updated_hardflow_text,
            encoding="utf-8",
            file_mode=0o640,
            dir_mode=0o750,
        )

    profile_snapshot = write_profile_snapshot(tier_key=tier_key, profile=profile)
    print(f"backup_dir={backup_dir}")
    print(f"profile_snapshot={profile_snapshot}")
    print("status=ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Bootstrap local OpenClaw runtime agents from repository config."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
AGENT_FILES = ("SOUL.md", "models.json", "auth.json", "auth-profiles.json")


def now_stamp() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def parse_json_output(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for candidate in reversed(lines):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    try:
        payload = json.loads(text)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_openclaw_path(value: str, openclaw_home: Path) -> str:
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""

    marker = "/.openclaw/"
    if marker in text:
        suffix = text.split(marker, 1)[1].lstrip("/")
        return str((openclaw_home / Path(suffix)).resolve())

    if text.startswith("~/.openclaw/"):
        return str((openclaw_home / Path(text[len("~/.openclaw/") :])).resolve())

    if text.startswith(str(openclaw_home).replace("\\", "/")):
        return str(Path(text).resolve())

    if text.startswith("/"):
        return str(Path(text))

    return str((openclaw_home / Path(text)).resolve())


def detect_available_models(openclaw_bin: str) -> list[str]:
    openclaw_cmd = str(openclaw_bin or "openclaw").strip() or "openclaw"
    resolved = shutil.which(openclaw_cmd) or shutil.which(f"{openclaw_cmd}.cmd")
    if resolved:
        cmd = [resolved, "models", "status", "--json"]
    else:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"{openclaw_cmd} models status --json",
        ]
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=25,
            check=False,
        )
    except Exception:
        return []
    payload = parse_json_output(proc.stdout) or {}
    seen: set[str] = set()
    out: list[str] = []
    allowed = payload.get("allowed")
    if isinstance(allowed, list):
        for item in allowed:
            model = str(item or "").strip()
            if model and model not in seen:
                out.append(model)
                seen.add(model)
    for key in ("resolvedDefault", "defaultModel"):
        model = str(payload.get(key, "")).strip()
        if model and model not in seen:
            out.append(model)
            seen.add(model)
    return out


def choose_fallback_model(local_cfg: dict[str, Any], available_models: list[str], explicit_fallback: str) -> str:
    candidates = [
        str(explicit_fallback or "").strip(),
        str(local_cfg.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")).strip(),
        "volcengine/kimi-k2.5",
    ]
    if available_models:
        for candidate in candidates:
            if candidate and candidate in available_models:
                return candidate
        return available_models[0]
    for candidate in candidates:
        if candidate:
            return candidate
    return "volcengine/kimi-k2.5"


def sanitize_config_compat(config: dict[str, Any]) -> None:
    agents = config.get("agents")
    if isinstance(agents, dict):
        defaults = agents.get("defaults")
        if isinstance(defaults, dict):
            defaults.pop("outputPolicy", None)
            subagents = defaults.get("subagents")
            if isinstance(subagents, dict):
                subagents.pop("maxSpawnDepth", None)
                subagents.pop("maxChildrenPerAgent", None)

    commands = config.get("commands")
    if isinstance(commands, dict):
        commands.pop("ownerDisplay", None)

    channels = config.get("channels")
    if isinstance(channels, dict):
        telegram = channels.get("telegram")
        if isinstance(telegram, dict):
            telegram.pop("streaming", None)


def ensure_bindings(local_cfg: dict[str, Any], repo_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    bindings: list[dict[str, Any]] = []
    local_bindings = local_cfg.get("bindings")
    if isinstance(local_bindings, list):
        bindings.extend([x for x in local_bindings if isinstance(x, dict)])

    repo_bindings = repo_cfg.get("bindings")
    if isinstance(repo_bindings, list):
        for item in repo_bindings:
            if not isinstance(item, dict):
                continue
            bindings.append(item)

    has_coordinator = False
    for item in bindings:
        if str(item.get("agentId", "")).strip() == "coordinator":
            has_coordinator = True
            break

    if not has_coordinator:
        bindings.append({"agentId": "coordinator", "match": {"channel": "telegram"}})

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in bindings:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def merge_agents(
    local_cfg: dict[str, Any],
    repo_cfg: dict[str, Any],
    openclaw_home: Path,
    available_models: list[str],
    fallback_model: str,
    force_model: str,
) -> list[dict[str, Any]]:
    local_agents = local_cfg.get("agents", {}).get("list", [])
    local_map: dict[str, dict[str, Any]] = {}
    if isinstance(local_agents, list):
        for item in local_agents:
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("id", "")).strip()
            if agent_id:
                local_map[agent_id] = dict(item)

    repo_agents = repo_cfg.get("agents", {}).get("list", [])
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    if isinstance(repo_agents, list):
        for item in repo_agents:
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("id", "")).strip()
            if not agent_id:
                continue

            base = dict(local_map.get(agent_id, {}))
            base["id"] = agent_id
            base["name"] = str(item.get("name", "")).strip() or base.get("name") or agent_id

            workspace = normalize_openclaw_path(str(item.get("workspace", "")).strip(), openclaw_home)
            if not workspace:
                workspace = str((openclaw_home / ("workspace" if agent_id == "main" else f"workspace-{agent_id}")).resolve())
            base["workspace"] = workspace

            agent_dir = normalize_openclaw_path(str(item.get("agentDir", "")).strip(), openclaw_home)
            if not agent_dir:
                agent_dir = str((openclaw_home / "agents" / agent_id / "agent").resolve())
            base["agentDir"] = agent_dir

            preferred_model = str(item.get("model", "")).strip() or str(base.get("model", "")).strip()
            model = force_model or preferred_model or fallback_model
            if available_models and model not in available_models:
                model = fallback_model
            base["model"] = model

            subagents = item.get("subagents")
            if isinstance(subagents, dict):
                allow_agents = subagents.get("allowAgents")
                if isinstance(allow_agents, list):
                    base["subagents"] = {"allowAgents": [str(x).strip() for x in allow_agents if str(x).strip()]}

            merged.append(base)
            seen.add(agent_id)

    for agent_id, item in local_map.items():
        if agent_id in seen:
            continue
        merged.append(item)

    merged.sort(key=lambda x: (0 if str(x.get("id", "")).strip() == "main" else 1, str(x.get("id", ""))))
    return merged


def ensure_agent_to_agent(local_cfg: dict[str, Any], repo_cfg: dict[str, Any], merged_agents: list[dict[str, Any]]) -> dict[str, Any]:
    allow: list[str] = []
    repo_allow = (
        repo_cfg.get("tools", {})
        .get("agentToAgent", {})
        .get("allow", [])
    )
    if isinstance(repo_allow, list):
        allow.extend([str(x).strip() for x in repo_allow if str(x).strip()])
    if not allow:
        allow.extend([str(x.get("id", "")).strip() for x in merged_agents if str(x.get("id", "")).strip()])

    unique_allow: list[str] = []
    seen: set[str] = set()
    for agent_id in allow:
        key = agent_id.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_allow.append(agent_id)

    tools = local_cfg.setdefault("tools", {})
    if not isinstance(tools, dict):
        tools = {}
        local_cfg["tools"] = tools
    a2a = tools.setdefault("agentToAgent", {})
    if not isinstance(a2a, dict):
        a2a = {}
        tools["agentToAgent"] = a2a
    a2a["enabled"] = True
    a2a["allow"] = unique_allow
    return a2a


def copy_agent_files(repo_root: Path, openclaw_home: Path, agent_ids: list[str], dry_run: bool) -> dict[str, list[str]]:
    copied: list[str] = []
    skipped: list[str] = []
    missing_sources: list[str] = []

    for agent_id in agent_ids:
        src_dir = repo_root / "agents" / agent_id
        if not src_dir.exists():
            missing_sources.append(str(src_dir))
            continue
        dst_dir = openclaw_home / "agents" / agent_id / "agent"
        if not dry_run:
            dst_dir.mkdir(parents=True, exist_ok=True)
            workspace = openclaw_home / ("workspace" if agent_id == "main" else f"workspace-{agent_id}")
            workspace.mkdir(parents=True, exist_ok=True)
        for filename in AGENT_FILES:
            src = src_dir / filename
            if not src.exists():
                skipped.append(f"{agent_id}/{filename}")
                continue
            dst = dst_dir / filename
            if not dry_run:
                shutil.copy2(src, dst)
            copied.append(f"{agent_id}/{filename}")

    return {
        "copied": copied,
        "skipped": skipped,
        "missing_sources": missing_sources,
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    home = Path.home()

    parser = argparse.ArgumentParser(description="Bootstrap runtime agents from repository config")
    parser.add_argument("--repo-config", default=str(repo_root / "openclaw" / "openclaw.json"))
    parser.add_argument("--local-config", default=str(home / ".openclaw" / "openclaw.json"))
    parser.add_argument("--openclaw-home", default=str(home / ".openclaw"))
    parser.add_argument("--openclaw-bin", default="openclaw")
    parser.add_argument("--fallback-model", default="volcengine/kimi-k2.5")
    parser.add_argument("--force-model", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    repo_config_path = Path(args.repo_config).expanduser()
    local_config_path = Path(args.local_config).expanduser()
    openclaw_home = Path(args.openclaw_home).expanduser()

    repo_cfg = load_json(repo_config_path)
    local_cfg = load_json(local_config_path)
    if not repo_cfg:
        payload = {"ok": False, "error": f"repo_config_invalid:{repo_config_path}"}
        print(json.dumps(payload, ensure_ascii=False))
        return 2
    if not local_cfg:
        payload = {"ok": False, "error": f"local_config_invalid:{local_config_path}"}
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    available_models = detect_available_models(str(args.openclaw_bin))
    fallback_model = choose_fallback_model(
        local_cfg=local_cfg,
        available_models=available_models,
        explicit_fallback=str(args.fallback_model),
    )
    force_model = str(args.force_model or "").strip()
    if force_model and available_models and force_model not in available_models:
        payload = {
            "ok": False,
            "error": f"force_model_not_available:{force_model}",
            "available_models": available_models,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 2
    if not force_model and not available_models:
        force_model = fallback_model

    merged_agents = merge_agents(
        local_cfg,
        repo_cfg,
        openclaw_home=openclaw_home,
        available_models=available_models,
        fallback_model=fallback_model,
        force_model=force_model,
    )
    local_cfg.setdefault("agents", {})
    if not isinstance(local_cfg["agents"], dict):
        local_cfg["agents"] = {}
    local_cfg["agents"]["list"] = merged_agents

    a2a = ensure_agent_to_agent(local_cfg, repo_cfg, merged_agents=merged_agents)
    local_cfg["bindings"] = ensure_bindings(local_cfg, repo_cfg)
    sanitize_config_compat(local_cfg)

    agent_ids = [str(item.get("id", "")).strip() for item in merged_agents if str(item.get("id", "")).strip()]
    copy_result = copy_agent_files(
        repo_root=repo_root,
        openclaw_home=openclaw_home,
        agent_ids=agent_ids,
        dry_run=bool(args.dry_run),
    )

    backup_path = ""
    if not args.dry_run:
        backup_path = str(local_config_path.with_name(f"{local_config_path.name}.bak.bootstrap.{now_stamp()}"))
        shutil.copy2(local_config_path, backup_path)
        write_json(local_config_path, local_cfg)

    result = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "repo_config": str(repo_config_path),
        "local_config": str(local_config_path),
        "backup": backup_path,
        "agents_count": len(agent_ids),
        "agent_ids": agent_ids,
        "agent_to_agent": a2a,
        "available_models": available_models,
        "fallback_model": fallback_model,
        "force_model": force_model,
        "bindings_count": len(local_cfg.get("bindings", [])) if isinstance(local_cfg.get("bindings"), list) else 0,
        "copied_files_count": len(copy_result.get("copied", [])),
        "copy_result": copy_result,
    }
    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

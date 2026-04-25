#!/usr/bin/env python3
"""Project-specific entrypoint for SmartMultiPlatformArbitrage pipeline runs."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_KEY = "smart-multi-platform-arbitrage"
RUNTIME_HOME = Path("/home/arbops/.hermes")
PROJECT_DIR = Path("/home/arbops/projects/SmartMultiPlatformArbitrage")
OPS_DIR = RUNTIME_HOME / "ops"
RUNNER = OPS_DIR / "pipeline_runner.py"
BRIDGE = OPS_DIR / "smart_arb_live_bridge.py"
WORKSPACE_ROOT = RUNTIME_HOME / "pipeline-runs"
PROJECT_MEMORY_ROOT = PROJECT_DIR / "memory"
TASK_CENTER_DB = OPS_DIR / "task-center" / "task_center.db"


def utc_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_prefix = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in prefix).strip("-")
    return f"{safe_prefix or 'discord'}-{stamp}"


def option_present(args: list[str], option: str) -> bool:
    return any(item == option or item.startswith(option + "=") for item in args)


def bridge_command(stage: str, args: argparse.Namespace) -> str:
    command = [
        sys.executable,
        str(BRIDGE),
        "--stage",
        stage,
        "--profile",
        args.profile,
        "--agent-mode",
        args.live_bridge_agent_mode,
        "--provider",
        args.live_bridge_provider,
        "--model",
        args.live_bridge_model,
    ]
    if stage == "code_execution" and not args.live_bridge_no_yolo:
        command.append("--allow-yolo")
        command.extend(["--max-turns", str(args.live_bridge_code_max_turns)])
    elif stage in {"external_research", "requirements_discussion", "code_review"}:
        command.extend(["--max-turns", str(args.live_bridge_agent_max_turns)])
    if stage == "deployment" and not args.no_internal_api_restart:
        command.append("--allow-internal-api-restart")
    return " ".join(shlex.quote(str(part)) for part in command)


def default_live_bridge_args(args: argparse.Namespace, passthrough: list[str]) -> list[str]:
    if not args.live or args.no_live_bridge:
        return []

    injected: list[str] = []
    command_options = [
        ("--research-command", "external_research"),
        ("--requirements-discussion-command", "requirements_discussion"),
        ("--code-command", "code_execution"),
        ("--verification-command", "verification"),
        ("--code-review-command", "code_review"),
        ("--deployment-command", "deployment"),
        ("--memory-write-command", "memory_writeback"),
    ]
    for option, stage in command_options:
        if not option_present(passthrough, option):
            injected.extend([option, bridge_command(stage, args)])
    if not option_present(passthrough, "--command-timeout-seconds"):
        injected.extend(["--command-timeout-seconds", str(args.live_bridge_timeout_seconds)])
    return injected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart arbitrage project delivery pipeline entry")
    parser.add_argument("--source", default="discord")
    parser.add_argument("--profile", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_PROFILE", "arbitrageagent"))
    parser.add_argument("--live", action="store_true", help="require live implementation, verification, review and memory evidence")
    parser.add_argument("--no-live-bridge", action="store_true", help="do not inject default live evidence commands")
    parser.add_argument("--live-bridge-agent-mode", choices=["hermes", "echo"], default=os.environ.get("SMART_ARB_LIVE_BRIDGE_AGENT_MODE", "hermes"))
    parser.add_argument("--live-bridge-provider", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_PROVIDER", "openai-codex"))
    parser.add_argument("--live-bridge-model", default=os.environ.get("SMART_ARB_LIVE_BRIDGE_MODEL", "gpt-5.5"))
    parser.add_argument("--live-bridge-timeout-seconds", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_TIMEOUT_SECONDS", "1800")))
    parser.add_argument("--live-bridge-agent-max-turns", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_AGENT_MAX_TURNS", "24")))
    parser.add_argument("--live-bridge-code-max-turns", type=int, default=int(os.environ.get("SMART_ARB_LIVE_BRIDGE_CODE_MAX_TURNS", "60")))
    parser.add_argument("--live-bridge-no-yolo", action="store_true", help="do not let Hermes bypass command approvals for code execution")
    parser.add_argument("--no-internal-api-restart", action="store_true", help="do not restart the internal FastAPI tmux service in deployment stage")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, passthrough = parser.parse_known_args(argv)

    profile = args.profile or "arbitrageagent"
    run_id = utc_run_id(f"{args.source}-{profile}")
    cmd = [
        sys.executable,
        str(RUNNER),
        "--project-key",
        PROJECT_KEY,
        "--runtime-host",
        "hermes",
        "--runtime-home",
        str(RUNTIME_HOME),
        "--workspace-root",
        str(WORKSPACE_ROOT),
        "--project-memory-root",
        str(PROJECT_MEMORY_ROOT),
        "--command-cwd",
        str(PROJECT_DIR),
        "--record-task-center",
        "--task-center-db",
        str(TASK_CENTER_DB),
        "--write-project-memory",
        "--run-id",
        run_id,
        "--source-url",
        f"{args.source}:{profile}",
        "--force",
        "--emit-json",
    ]
    if not args.live:
        cmd.append("--dry-run")

    cmd += default_live_bridge_args(args, passthrough)
    cmd += passthrough
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_DIR),
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Project-specific entrypoint for SmartMultiPlatformArbitrage pipeline runs."""

from __future__ import annotations

import argparse
import json
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
STAGE_AGENT_MAP = {
    "intake": "coordinator",
    "context_snapshot": "project-agent",
    "project_memory_context": "project-agent",
    "external_research": "web-agent",
    "requirements_package": "project-agent",
    "requirements_discussion": "project-agent,reviewer",
    "requirements_review": "reviewer",
    "solution_package": "project-agent",
    "solution_review": "reviewer",
    "code_execution": "backend-dev",
    "verification": "tester",
    "code_review": "reviewer",
    "deployment": "deployer",
    "acceptance": "tester",
    "writeback": "doc-writer",
}
STAGE_LABELS = {
    "intake": "任务接入",
    "context_snapshot": "上下文快照",
    "project_memory_context": "项目记忆读取",
    "external_research": "外部资料核对",
    "requirements_package": "需求整理",
    "requirements_discussion": "双 AI 需求讨论",
    "requirements_review": "需求评审",
    "solution_package": "方案整理",
    "solution_review": "方案评审",
    "code_execution": "代码执行",
    "verification": "验证",
    "code_review": "代码审查",
    "deployment": "内部部署",
    "acceptance": "验收",
    "writeback": "记忆写回",
}
STATUS_LABELS = {
    "completed": "完成",
    "blocked": "阻塞",
    "failed": "失败",
    "passed": "通过",
}


def utc_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    safe_prefix = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in prefix).strip("-")
    return f"{safe_prefix or 'discord'}-{stamp}"


def option_present(args: list[str], option: str) -> bool:
    return any(item == option or item.startswith(option + "=") for item in args)


def compact_text(value: object, limit: int = 120) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def parse_runner_state(stdout: str) -> dict | None:
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) and "stages" in payload else None


def stage_artifact_name(stage: dict) -> str:
    artifact = str(stage.get("artifact") or "").strip()
    if not artifact:
        return ""
    return Path(artifact).name


def render_stage_line(stage: dict) -> str:
    name = str(stage.get("name") or "").strip()
    label = STAGE_LABELS.get(name, name or "未知阶段")
    agent = STAGE_AGENT_MAP.get(name, "coordinator")
    status = str(stage.get("status") or "").strip()
    status_label = STATUS_LABELS.get(status, status or "未知")
    parts = [f"{label}: {agent} -> {status_label}"]
    verdict = str(stage.get("verdict") or "").strip()
    if verdict:
        parts.append(f"结论={verdict}")
    score = stage.get("score")
    if score is not None:
        parts.append(f"分数={score}")
    artifact_name = stage_artifact_name(stage)
    if artifact_name:
        parts.append(f"证据={artifact_name}")
    next_action = str(stage.get("next_action") or "").strip()
    if status != "completed" and next_action:
        parts.append(f"下一步={next_action}")
    return "- " + "；".join(parts)


def render_chat_summary(
    state: dict | None,
    *,
    source: str,
    profile: str,
    returncode: int,
    raw_stdout: str = "",
    raw_stderr: str = "",
    stage_limit: int = 20,
) -> str:
    if not state:
        tail = compact_text((raw_stderr or raw_stdout or "pipeline runner 没有返回可解析状态"), 360)
        return "\n".join(
            [
                "# nofx 任务执行状态",
                f"- 来源: {source}/{profile}",
                f"- 状态: 无法解析 pipeline JSON，returncode={returncode}",
                f"- 输出: {tail}",
            ]
        )

    status = str(state.get("status") or "").strip()
    status_label = "已完成" if status == "completed" else "已阻塞" if status == "blocked" else status or "未知"
    stages = [item for item in state.get("stages", []) if isinstance(item, dict)]
    completed = sum(1 for item in stages if item.get("status") == "completed")
    blocked = len(stages) - completed
    task_center = state.get("task_center") if isinstance(state.get("task_center"), dict) else {}
    task_id = str(task_center.get("task_id") or "未记录").strip()
    failed_stage = str(state.get("failed_stage") or "none").strip()
    next_action = str(state.get("next_action") or "none").strip()
    run_dir = str(state.get("run_dir") or "").strip()

    lines = [
        "# nofx 任务执行状态",
        f"- 来源: {source}/{profile}",
        f"- Run ID: {state.get('run_id', '-')}",
        f"- 总状态: {status_label}",
        f"- Task Center: {task_id}",
        f"- 阶段进度: {completed}/{len(stages)} 完成，阻塞 {blocked}",
        f"- 下一步: {next_action}；失败阶段: {failed_stage}",
    ]
    if run_dir:
        lines.append(f"- 证据目录: {run_dir}")

    lines.append("")
    lines.append("## agent 分工与完成情况")
    for stage in stages[: max(1, int(stage_limit or 20))]:
        lines.append(render_stage_line(stage))
    if len(stages) > stage_limit:
        lines.append(f"- 还有 {len(stages) - stage_limit} 个阶段未展开，详见 pipeline_state.json")

    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    key_artifacts = [
        key
        for key in (
            "requirements_discussion",
            "verification",
            "code_review",
            "deployment",
            "acceptance",
            "delivery_evidence",
            "writeback",
        )
        if key in artifacts
    ]
    if key_artifacts:
        lines.append("")
        lines.append(f"关键证据: {', '.join(key_artifacts)}")
    return "\n".join(lines)


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
    parser.add_argument("--emit-json", action="store_true", help="print raw pipeline JSON instead of the chat summary")
    parser.add_argument("--no-chat-summary", action="store_true", help="print raw runner output without the chat summary")
    parser.add_argument("--chat-stage-limit", type=int, default=int(os.environ.get("SMART_ARB_CHAT_STAGE_LIMIT", "20")))
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
        capture_output=True,
        check=False,
    )
    if args.emit_json or args.no_chat_summary:
        if proc.stdout:
            print(proc.stdout.rstrip())
        if proc.stderr:
            print(proc.stderr.rstrip(), file=sys.stderr)
    else:
        state = parse_runner_state(proc.stdout)
        print(
            render_chat_summary(
                state,
                source=args.source,
                profile=profile,
                returncode=int(proc.returncode),
                raw_stdout=proc.stdout,
                raw_stderr=proc.stderr,
                stage_limit=args.chat_stage_limit,
            )
        )
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

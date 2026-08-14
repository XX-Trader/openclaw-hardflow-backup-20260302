#!/usr/bin/env python3
"""逐宿主探测 Hermes / OpenClaw 运行环境与关键路径。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable


def _configure_utf8_stdio() -> None:
    """尽量复用仓库现有 UTF-8 运行时配置，失败时保持静默降级。"""
    shared_dir = Path(__file__).resolve().parents[4] / "scripts" / "openclaw-ops" / "shared"
    if str(shared_dir) not in sys.path:
        sys.path.insert(0, str(shared_dir))
    try:
        from utf8_runtime import configure_process_utf8_stdio  # type: ignore
    except Exception:
        return
    configure_process_utf8_stdio()


_configure_utf8_stdio()

SUPPORTED_HOSTS = {"openclaw", "hermes"}
SUPPORTED_RUNTIME_KINDS = {"windows", "linux", "wsl"}


@dataclass(frozen=True)
class RuntimeProbeResult:
    """描述单个宿主最终解析出的运行环境与关键路径。"""

    host: str
    runtime_kind: str
    transport: str
    distro: str
    home: str
    session_roots: list[str]
    hot_memory_paths: dict[str, str]
    workspace_roots: list[str]
    state_db: str

    def to_dict(self) -> dict[str, Any]:
        """把探测结果转成可序列化字典。"""
        return asdict(self)


@dataclass(frozen=True)
class ParserCandidatePacket:
    """共享的宿主内 Parser Agent 候选输入封包。"""

    candidate_id: str
    host: str
    project: str
    trace_id: str
    task_id: str
    run_id: str
    source: str
    evidence_refs: list[str]
    window_text: str
    target_schema_version: str

    def to_dict(self) -> dict[str, Any]:
        """把候选封包转成可序列化字典。"""
        return asdict(self)


def normalize_runtime_kind(value: str | None, *, current_os: str) -> str:
    """把外部传入的 runtime kind 规范成受支持的固定集合。"""
    text = str(value or "").strip().lower()
    if text in SUPPORTED_RUNTIME_KINDS:
        return text
    return "windows" if current_os == "windows" else "linux"


def normalize_hosts(value: Iterable[str] | str | None) -> list[str]:
    """把 CLI 或调用方传入的宿主列表规范成去重后的有序列表。"""
    if value is None:
        items = ["openclaw", "hermes"]
    elif isinstance(value, str):
        items = [part.strip().lower() for part in value.split(",") if part.strip()]
    else:
        items = [str(part).strip().lower() for part in value if str(part).strip()]

    normalized: list[str] = []
    for item in items:
        if item not in SUPPORTED_HOSTS:
            raise ValueError(f"unsupported_host:{item}")
        if item not in normalized:
            normalized.append(item)
    return normalized


def _runtime_path(value: str | Path, runtime_kind: str) -> PurePosixPath | PureWindowsPath:
    """按目标运行时而不是探测器宿主解释路径分隔符。"""
    path_type = PureWindowsPath if runtime_kind == "windows" else PurePosixPath
    return path_type(str(value))


def build_openclaw_probe_result(
    *,
    current_os: str,
    user_home: Path,
    runtime_kind_override: str | None = None,
    home_override: str | None = None,
) -> RuntimeProbeResult:
    """构建 OpenClaw 宿主的探测结果。"""
    runtime_kind = normalize_runtime_kind(runtime_kind_override, current_os=current_os)
    if home_override:
        home = _runtime_path(home_override, runtime_kind)
    else:
        home = _runtime_path(user_home, runtime_kind) / ".openclaw"

    return RuntimeProbeResult(
        host="openclaw",
        runtime_kind=runtime_kind,
        transport="native_fs" if runtime_kind != "wsl" else "wsl_exec",
        distro="",
        home=str(home),
        session_roots=[str(home / "agents" / "*" / "sessions" / "*.jsonl")],
        hot_memory_paths={
            "user": str(home / "workspace*" / "USER.md"),
            "memory": str(home / "workspace*" / "MEMORY.md"),
        },
        workspace_roots=[str(home / "workspace*")],
        state_db="",
    )


def build_hermes_probe_result(
    *,
    current_os: str,
    user_home: Path,
    runtime_kind_override: str | None = None,
    home_override: str | None = None,
    hermes_wsl_distro: str | None = None,
    hermes_wsl_user: str | None = None,
) -> RuntimeProbeResult:
    """构建 Hermes 宿主的探测结果。"""
    runtime_kind = normalize_runtime_kind(runtime_kind_override, current_os=current_os)
    if not runtime_kind_override and not home_override and current_os == "windows":
        runtime_kind = "wsl"

    if runtime_kind == "wsl":
        distro = str(hermes_wsl_distro or "Ubuntu").strip() or "Ubuntu"
        wsl_user = str(hermes_wsl_user or "ubuntu").strip() or "ubuntu"
        home_path = _runtime_path(home_override or f"/home/{wsl_user}/.hermes", runtime_kind)
        return RuntimeProbeResult(
            host="hermes",
            runtime_kind="wsl",
            transport="wsl_exec",
            distro=distro,
            home=str(home_path),
            session_roots=[str(home_path / "sessions")],
            hot_memory_paths={
                "user": str(home_path / "memories" / "USER.md"),
                "memory": str(home_path / "memories" / "MEMORY.md"),
            },
            workspace_roots=[],
            state_db=str(home_path / "state.db"),
        )

    if home_override:
        home_path = _runtime_path(home_override, runtime_kind)
    else:
        home_path = _runtime_path(user_home, runtime_kind) / ".hermes"

    return RuntimeProbeResult(
        host="hermes",
        runtime_kind=runtime_kind,
        transport="native_fs",
        distro="",
        home=str(home_path),
        session_roots=[str(home_path / "sessions")],
        hot_memory_paths={
            "user": str(home_path / "memories" / "USER.md"),
            "memory": str(home_path / "memories" / "MEMORY.md"),
        },
        workspace_roots=[],
        state_db=str(home_path / "state.db"),
    )


def probe_hosts(
    *,
    hosts: Iterable[str] | str | None = None,
    current_os: str | None = None,
    user_home: Path | None = None,
    openclaw_runtime_kind: str | None = None,
    hermes_runtime_kind: str | None = None,
    openclaw_home: str | None = None,
    hermes_home: str | None = None,
    hermes_wsl_distro: str | None = None,
    hermes_wsl_user: str | None = None,
) -> dict[str, dict[str, Any]]:
    """按宿主返回结构化探测结果。"""
    normalized_hosts = normalize_hosts(hosts)
    normalized_os = str(current_os or ("windows" if os.name == "nt" else "linux")).strip().lower()
    normalized_home = user_home or Path.home()

    results: dict[str, dict[str, Any]] = {}
    for host in normalized_hosts:
        if host == "openclaw":
            probe_result = build_openclaw_probe_result(
                current_os=normalized_os,
                user_home=normalized_home,
                runtime_kind_override=openclaw_runtime_kind,
                home_override=openclaw_home,
            )
        else:
            probe_result = build_hermes_probe_result(
                current_os=normalized_os,
                user_home=normalized_home,
                runtime_kind_override=hermes_runtime_kind,
                home_override=hermes_home,
                hermes_wsl_distro=hermes_wsl_distro,
                hermes_wsl_user=hermes_wsl_user,
            )
        results[host] = probe_result.to_dict()
    return results


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(description="Probe Hermes/OpenClaw runtime paths for shared distillation")
    parser.add_argument("--hosts", default="openclaw,hermes", help="comma-separated hosts")
    parser.add_argument("--openclaw-home", default="", help="override OpenClaw home")
    parser.add_argument("--hermes-home", default="", help="override Hermes home")
    parser.add_argument("--openclaw-runtime-kind", default="", choices=["", "windows", "linux", "wsl"])
    parser.add_argument("--hermes-runtime-kind", default="", choices=["", "windows", "linux", "wsl"])
    parser.add_argument("--hermes-wsl-distro", default="Ubuntu")
    parser.add_argument("--hermes-wsl-user", default="ubuntu")
    parser.add_argument("--emit-json", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    result = probe_hosts(
        hosts=args.hosts,
        openclaw_runtime_kind=str(args.openclaw_runtime_kind or "").strip() or None,
        hermes_runtime_kind=str(args.hermes_runtime_kind or "").strip() or None,
        openclaw_home=str(args.openclaw_home or "").strip() or None,
        hermes_home=str(args.hermes_home or "").strip() or None,
        hermes_wsl_distro=str(args.hermes_wsl_distro or "").strip() or None,
        hermes_wsl_user=str(args.hermes_wsl_user or "").strip() or None,
    )

    if args.emit_json or args.dry_run:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for host, payload in result.items():
            print(f"[{host}] runtime={payload['runtime_kind']} home={payload['home']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

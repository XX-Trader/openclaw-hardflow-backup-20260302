#!/usr/bin/env python3
"""Hermes 宿主适配器：负责封装 Parser Agent 请求。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime_probe import ParserCandidatePacket, RuntimeProbeResult  # type: ignore  # noqa: E402


def build_parser_request(
    runtime_result: RuntimeProbeResult,
    packet: ParserCandidatePacket,
) -> dict[str, Any]:
    """把 Hermes 宿主探测结果和候选封包整理成统一请求。"""
    if runtime_result.host != "hermes":
        raise ValueError("runtime_host_mismatch:expected=hermes")
    if packet.host != "hermes":
        raise ValueError("packet_host_mismatch:expected=hermes")

    return {
        "host": "hermes",
        "agent": "hermes-parser",
        "transport": runtime_result.transport,
        "runtime": runtime_result.to_dict(),
        "parser_input": packet.to_dict(),
    }

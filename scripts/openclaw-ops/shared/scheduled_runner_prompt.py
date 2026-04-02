#!/usr/bin/env python3
"""Shared scheduled-runner prompt builder."""

from __future__ import annotations

from typing import Iterable


def _normalize_rules(extra_rules: Iterable[str] | None = None) -> list[str]:
    normalized_rules: list[str] = []
    if extra_rules is None:
        return normalized_rules
    for item in extra_rules:
        text = str(item or "").strip()
        if text:
            normalized_rules.append(text)
    return normalized_rules


def build_scheduled_runner_message(
    command: str,
    *,
    role: str,
    extra_rules: Iterable[str] | None = None,
    forbid_file_mutations: bool = True,
    forbid_file_inspection: bool = False,
) -> str:
    normalized_command = str(command or "").strip()
    rules = [
        "Execute the command exactly once.",
        "If the exec tool reports 'Command still running', do not start another exec command.",
        "You MUST wait for completion by using only process poll or process log for that same session until the process exits.",
        "Do not run unrelated follow-up commands or diagnostics.",
        "If the finished command prints NO_REPLY, you must respond exactly NO_REPLY and stop.",
        "If the finished command outputs a human-facing message, preserve the original Chinese text and UTC+8 timestamps exactly.",
        "Do not translate, paraphrase, summarize, explain, or add process commentary.",
        "Never output process filler sentences such as 'Let's run ...', 'Okay, ...', '我来执行一下', or '我再检查一下'.",
    ]
    rules.extend(_normalize_rules(extra_rules))
    guidance = " ".join(rules)

    prefix_lines = [
        f"You are {role}. Run command only:",
        normalized_command,
        "Your first assistant turn MUST contain exactly one exec tool call for that command and no text.",
    ]
    if forbid_file_mutations:
        prefix_lines.append("Do not write, edit, create, move, or delete any file.")
    if forbid_file_inspection:
        prefix_lines.append(
            "Do not inspect files, list directories, or run any other command such as ls, pwd, cat, grep, find, or python probes."
        )
    prefix_lines.append("Do not execute any other command.")
    prefix_lines.append(guidance)
    prefix_lines.append("Return EXACTLY raw stdout/stderr text from the finished command.")
    prefix_lines.append("Do not add explanation, greeting, or prefix text.")
    prefix_lines.append("If the finished output is empty, reply NO_REPLY.")
    return "\n".join(prefix_lines)

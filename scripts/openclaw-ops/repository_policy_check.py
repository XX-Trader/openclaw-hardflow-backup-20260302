#!/usr/bin/env python3
"""Check first-party files for domain coupling, secrets, and stale owners."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import unquote


TEXT_SUFFIXES = {"", ".cfg", ".csv", ".env", ".example", ".ini", ".js", ".json", ".jsonl", ".md", ".patch", ".ps1", ".py", ".service", ".sh", ".toml", ".ts", ".txt", ".yaml", ".yml"}
SKIP_PARTS = {".git", ".codex-tmp", ".pytest_cache", "__pycache__", "node_modules", "vendor"}
SELF_PATH = "scripts/openclaw-ops/repository_policy_check.py"
ARCHIVE_PREFIXES = ("docs/archive/", "docs/plans/archive/")
MARKDOWN_LINK_SKIP_PREFIXES = ("docs/archive/", "docs/plans/")

DOMAIN_PATTERNS = {
    "domain_zh": re.compile(
        r"金融|财经|股票|股市|证券|行情|回测|交易执行|量化交易|量化策略|套利|对冲|多头|空头|"
        r"(?<!再)做多|做空(?!白)|盘口|K线|币圈|加密货币|虚拟币|期货|期权|外汇|基金|债券|"
        r"可转债|涨停|跌停|竞价|主力资金|资金流|仓位|止损|止盈|买入|卖出|持仓|收益率|盈亏|价差"
    ),
    "domain_en": re.compile(
        r"\b(?:finance|financial|stocks?|trading|traders?|backtests?|backtesting|arbitrage|"
        r"cryptocurrency|crypto|bitcoin|ethereum|binance|forex|futures|brokerage|stockbrokers?|"
        r"hedging|orderbooks?|candlesticks?|ohlcv?|securities|quantitative[ -](?:trading|finance)|"
        r"market[ -]data|price[ -]feed)\b", re.IGNORECASE
    ),
    "legacy_owner": re.compile(r"nofx|smart[_-]?arb|sutu|trend[_ -]?backtest|arbitrageagent|spreadagent", re.IGNORECASE),
}
PERSONAL_PATH_PATTERN = re.compile(
    r"C:/Users/(?!<user>|\{user\}|RuntimeUser|User|test|other|alice|me|fixture-user|xxx|YourName)"
    r"([^/\s`\"']+)|/home/ubuntu\b",
    re.IGNORECASE,
)
JSON_SECRET_FIELD = re.compile(
    r'''(?im)["'](?P<field>api[_-]?key|apikey|bot[_-]?token|access[_-]?token|refresh[_-]?token|gateway[_-]?token|token|secret|password|passwd|cookie|authorization)["']\s*:\s*["'](?P<value>[^"'\r\n]+)["']'''
)
ENV_SECRET_FIELD = re.compile(
    r'''(?m)^\s*(?:export\s+)?(?P<field>(?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|COOKIE|AUTHORIZATION)(?:_[A-Z0-9_]+)?)\s*=\s*["']?(?P<value>[^"'\s#\r\n]+)'''
)
SECRET_VALUE_PATTERNS = {
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "telegram_token": re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "api_token": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
}
PLACEHOLDER_PATTERN = re.compile(
    r"^(?:\$\{|\$\(|\{\{|%[A-Z_]+%|<|\[|\$[A-Z_]+|your[-_]|test[-_]|dummy[-_]|fake[-_]|"
    r"example[-_]|fixture[-_]|sample[-_]|target[-_]|repo[-_]|local[-_]|runtime[-_]|redacted|"
    r"changeme|django-insecure-|none|null|true|false)", re.IGNORECASE
)
STALE_OWNER_PATTERN = re.compile(r"scripts/openclaw-ops/[A-Za-z0-9_./-]+\.py")
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\((?P<target>[^)]+)\)")


@dataclass(frozen=True)
class Finding:
    category: str
    path: str
    line: int
    preview: str


def run_git(repo: Path, args: list[str]) -> bytes:
    process = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args], cwd=repo, capture_output=True, check=False
    )
    if process.returncode != 0:
        stderr = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr}")
    return process.stdout


def repository_paths(repo: Path, *, include_untracked: bool = True) -> list[Path]:
    """Read UTF-8 paths from NUL-delimited Git output, including Chinese names."""

    raw = run_git(repo, ["ls-files", "-z"])
    if include_untracked:
        raw += run_git(repo, ["ls-files", "-z", "--others", "--exclude-standard"])
    decoded = {Path(item.decode("utf-8")) for item in raw.split(b"\0") if item}
    return sorted(decoded, key=lambda value: value.as_posix())


def is_scannable(relative: Path, path: Path) -> bool:
    if not path.is_file() or any(part in SKIP_PARTS for part in relative.parts):
        return False
    if relative.suffix.lower() not in TEXT_SUFFIXES:
        return False
    try:
        return path.stat().st_size <= 10 * 1024 * 1024
    except OSError:
        return False


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def compact_preview(value: str, limit: int = 90) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def secret_field_findings(relative: str, text: str) -> Iterable[Finding]:
    patterns = [JSON_SECRET_FIELD]
    if Path(relative).suffix.lower() in {".env", ".example", ".service", ".sh", ".yaml", ".yml"}:
        patterns.append(ENV_SECRET_FIELD)
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group("value").strip()
            field = match.group("field")
            if len(value) < 12 or PLACEHOLDER_PATTERN.search(value) or field.lower().endswith("_env"):
                continue
            yield Finding("secret_field", relative, line_number(text, match.start()), f"{field}=<redacted:{len(value)}>")


def markdown_link_findings(repo: Path, relative: str, text: str) -> Iterable[Finding]:
    if not relative.endswith(".md") or relative.startswith(MARKDOWN_LINK_SKIP_PREFIXES):
        return
    source_dir = (repo / relative).parent
    for match in MARKDOWN_LINK_PATTERN.finditer(text):
        raw_target = match.group("target").strip()
        target = raw_target[1:raw_target.find(">")].strip() if raw_target.startswith("<") and ">" in raw_target else raw_target.split(maxsplit=1)[0]
        if not target or target.startswith(("#", "http://", "https://", "mailto:", "data:", "file://")):
            continue
        target = unquote(target.split("#", 1)[0].split("?", 1)[0])
        if not target or "{{" in target or "}}" in target:
            continue
        candidate = repo / target.lstrip("/") if target.startswith("/") else source_dir / target
        if not candidate.exists():
            yield Finding(
                "broken_markdown_link",
                relative,
                line_number(text, match.start()),
                compact_preview(target),
            )


def scan_repository(repo: Path, *, include_untracked: bool = True) -> dict[str, object]:
    findings: list[Finding] = []
    scanned = 0
    for relative in repository_paths(repo, include_untracked=include_untracked):
        path = repo / relative
        if not is_scannable(relative, path):
            continue
        relative_text = relative.as_posix()
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1

        if relative_text != SELF_PATH:
            domain_text = text
            for category, pattern in DOMAIN_PATTERNS.items():
                scan_text = re.sub(r"[_-]+", " ", domain_text) if category == "domain_en" else domain_text
                for match in pattern.finditer(scan_text):
                    findings.append(Finding(category, relative_text, line_number(scan_text, match.start()), compact_preview(match.group(0))))
            normalized_path_text = text.replace("\\", "/")
            for match in PERSONAL_PATH_PATTERN.finditer(normalized_path_text):
                findings.append(Finding("personal_path", relative_text, line_number(normalized_path_text, match.start()), compact_preview(match.group(0))))
            findings.extend(secret_field_findings(relative_text, text))
            for category, pattern in SECRET_VALUE_PATTERNS.items():
                for match in pattern.finditer(text):
                    value = match.group(0)
                    findings.append(Finding(category, relative_text, line_number(text, match.start()), f"{value[:3]}...{value[-3:]}"))
            findings.extend(markdown_link_findings(repo, relative_text, text))

        if relative_text.startswith(ARCHIVE_PREFIXES) or relative_text == "vendor/README.md":
            continue
        for match in STALE_OWNER_PATTERN.finditer(text):
            owner = match.group(0)
            if not (repo / owner).is_file():
                findings.append(Finding("stale_owner_reference", relative_text, line_number(text, match.start()), owner))

    ordered = sorted(set(findings), key=lambda item: (item.category, item.path, item.line, item.preview))
    counts: dict[str, int] = {}
    for finding in ordered:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    return {
        "ok": not ordered,
        "files_scanned": scanned,
        "finding_count": len(ordered),
        "counts": counts,
        "findings": [asdict(item) for item in ordered],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--tracked-only", action="store_true")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--emit-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo = args.repo.expanduser().resolve()
    report = scan_repository(repo, include_untracked=not args.tracked_only)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_output:
        output = args.json_output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="")
    if args.emit_json or not args.json_output:
        print(rendered, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

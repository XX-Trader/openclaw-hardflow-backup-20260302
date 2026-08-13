#!/usr/bin/env python3
"""Extract Agent frontmatter into deterministic Markdown and JSON indexes."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def extract_frontmatter(file_path: Path) -> dict[str, str] | None:
    """Parse the simple scalar fields used by Agent Markdown files."""

    try:
        content = file_path.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    match = FRONTMATTER_PATTERN.search(content)
    if not match:
        return None
    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"\'')
    return metadata


def build_indexes(agents_dir: Path) -> tuple[str, dict[str, Any]]:
    """Build index payloads without reading machine-specific paths."""

    agents: list[dict[str, str]] = []
    categories: dict[str, list[dict[str, str]]] = defaultdict(list)
    for markdown_file in sorted(agents_dir.rglob("*.md")):
        metadata = extract_frontmatter(markdown_file)
        if not metadata or not metadata.get("name"):
            continue
        relative = markdown_file.relative_to(agents_dir).with_suffix("").as_posix()
        agent = {
            "name": metadata.get("name", ""),
            "description": metadata.get("description", ""),
            "category": metadata.get("category", "uncategorized"),
            "file": relative,
        }
        agents.append(agent)
        categories[agent["category"]].append(agent)

    agents.sort(key=lambda item: (item["name"], item["file"]))
    generated_at = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()
    lines = [
        "# Agent 索引",
        "",
        f"> 自动生成时间: {generated_at}",
        f"> Agent 总数: {len(agents)}",
        f"> 类别数: {len(categories)}",
        "",
        "## 分类",
    ]
    for category in sorted(categories):
        lines.extend(["", f"### {category}", "", "| Agent | 描述 |", "| --- | --- |"])
        for agent in sorted(categories[category], key=lambda item: item["name"]):
            description = agent["description"]
            if len(description) > 80:
                description = description[:77] + "..."
            lines.append(f"| [{agent['name']}]({agent['file']}.md) | {description} |")

    payload: dict[str, Any] = {
        "generated_at": generated_at,
        "total_agents": len(agents),
        "categories": {
            category: [item["name"] for item in sorted(items, key=lambda value: value["name"])]
            for category, items in sorted(categories.items())
        },
        "agents": agents,
    }
    return "\n".join(lines).rstrip() + "\n", payload


def default_agents_dir() -> Path:
    configured = os.environ.get("AGENTS_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / "agents"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents-dir", type=Path, default=default_agents_dir())
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data",
    )
    parser.add_argument("--emit-json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    agents_dir = args.agents_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not agents_dir.is_dir():
        raise FileNotFoundError(f"agents directory does not exist: {agents_dir}")

    markdown, payload = build_indexes(agents_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_file = output_dir / "AGENTS_INDEX.md"
    json_file = output_dir / "agents.json"
    markdown_file.write_text(markdown, encoding="utf-8", newline="")
    json_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="",
    )
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"[OK] agents={payload['total_agents']} output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

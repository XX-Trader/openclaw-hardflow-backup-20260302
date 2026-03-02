#!/usr/bin/env python3
"""Risk rule sync helper for chat-driven dynamic risk updates."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def load_routing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": "2026-03-02", "high_risk_keywords": [], "low_risk_keywords": []}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("routing file must be JSON object")
    data.setdefault("high_risk_keywords", [])
    data.setdefault("low_risk_keywords", [])
    if not isinstance(data["high_risk_keywords"], list):
        data["high_risk_keywords"] = []
    if not isinstance(data["low_risk_keywords"], list):
        data["low_risk_keywords"] = []
    return data


def save_routing(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def norm(text: str) -> str:
    return str(text or "").strip().lower()


def add_unique(items: list[str], values: list[str]) -> None:
    existing = {norm(x) for x in items}
    for value in values:
        v = str(value).strip()
        if not v:
            continue
        key = norm(v)
        if key not in existing:
            items.append(v)
            existing.add(key)


def remove_values(items: list[str], values: list[str]) -> list[str]:
    rm = {norm(x) for x in values if str(x).strip()}
    if not rm:
        return items
    return [x for x in items if norm(x) not in rm]


def classify_text(text: str, routing: dict[str, Any]) -> dict[str, Any]:
    sample = norm(text)
    high = [x for x in routing.get("high_risk_keywords", []) if norm(x) and norm(x) in sample]
    low = [x for x in routing.get("low_risk_keywords", []) if norm(x) and norm(x) in sample]
    level = "high" if high else "low"
    return {"risk_level": level, "hits": {"high": high, "low": low}}


DEFAULT_HIGH = [
    "api变更",
    "接口变更",
    "参数变更",
    "固定参数变更",
    "逻辑变更",
    "代码执行流程变更",
    "流程变更",
    "结构变更",
    "数据库结构变更",
    "迁移",
    "回滚",
    "权限变更",
    "安全策略变更",
]

DEFAULT_LOW = [
    "代码bug",
    "bug修复",
    "配置错误",
    "网络失败",
    "网络抖动",
    "cpu过高",
    "内存不足",
    "磁盘不足",
    "资源使用率高",
    "重复进程",
]


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Risk rule sync for dynamic routing")
    parser.add_argument(
        "--routing-file",
        default=str(home / ".openclaw/ops/policy/routing-rules.json"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="show current risk keyword rules")
    show.add_argument("--emit-json", action="store_true")

    set_cmd = sub.add_parser("set", help="set keyword risk level")
    set_cmd.add_argument("--keyword", action="append", required=True)
    set_cmd.add_argument("--level", choices=["high", "low"], required=True)
    set_cmd.add_argument("--emit-json", action="store_true")

    batch = sub.add_parser("batch", help="batch update keyword risk level")
    batch.add_argument("--add-high", action="append", default=[])
    batch.add_argument("--add-low", action="append", default=[])
    batch.add_argument("--remove-high", action="append", default=[])
    batch.add_argument("--remove-low", action="append", default=[])
    batch.add_argument("--apply-default-preset", action="store_true")
    batch.add_argument("--emit-json", action="store_true")

    cls = sub.add_parser("classify", help="classify text by current rules")
    cls.add_argument("--text", required=True)
    cls.add_argument("--emit-json", action="store_true")

    args = parser.parse_args()
    routing_path = Path(args.routing_file).expanduser()
    routing = load_routing(routing_path)

    if args.command == "show":
        result = {
            "routing_file": str(routing_path),
            "high_risk_keywords": routing.get("high_risk_keywords", []),
            "low_risk_keywords": routing.get("low_risk_keywords", []),
        }
        if args.emit_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "classify":
        result = classify_text(args.text, routing)
        if args.emit_json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    high = [str(x) for x in routing.get("high_risk_keywords", [])]
    low = [str(x) for x in routing.get("low_risk_keywords", [])]

    if args.command == "set":
        values = [str(x).strip() for x in args.keyword if str(x).strip()]
        high = remove_values(high, values)
        low = remove_values(low, values)
        if args.level == "high":
            add_unique(high, values)
        else:
            add_unique(low, values)
    elif args.command == "batch":
        if args.apply_default_preset:
            add_unique(high, DEFAULT_HIGH)
            add_unique(low, DEFAULT_LOW)
        add_unique(high, [str(x) for x in args.add_high])
        add_unique(low, [str(x) for x in args.add_low])
        high = remove_values(high, [str(x) for x in args.remove_high])
        low = remove_values(low, [str(x) for x in args.remove_low])
        overlap = {norm(x) for x in high} & {norm(x) for x in low}
        if overlap:
            low = [x for x in low if norm(x) not in overlap]

    routing["version"] = "2026-03-02"
    routing["high_risk_keywords"] = high
    routing["low_risk_keywords"] = low
    save_routing(routing_path, routing)

    result = {
        "updated": True,
        "routing_file": str(routing_path),
        "high_risk_count": len(high),
        "low_risk_count": len(low),
    }
    if getattr(args, "emit_json", False):
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

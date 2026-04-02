#!/usr/bin/env python3
"""Detect OpenClaw installations and recommend a target home directory."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
PRUNE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def split_path_like(value: str) -> list[str]:
    if not value:
        return []
    text = value.replace(",", os.pathsep).replace(";", os.pathsep)
    return [x.strip() for x in text.split(os.pathsep) if x.strip()]


def safe_resolve(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.exists():
        return expanded.resolve()
    try:
        return expanded.resolve()
    except Exception:
        return expanded.absolute()


def parse_version_from_config(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    for key in ("version", "openclawVersion", "buildVersion", "release"):
        raw = str(data.get(key, "")).strip()
        if raw:
            return raw
    return ""


def read_jobs_count(path: Path) -> int:
    if not path.exists():
        return -1
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return -1
    if isinstance(data, dict) and isinstance(data.get("jobs"), list):
        return len(data["jobs"])
    return -1


def inspect_installation(path: Path, source: str) -> dict[str, Any]:
    home = safe_resolve(path)
    openclaw_json = home / "openclaw.json"
    openclaw_sub_json = home / "openclaw" / "openclaw.json"
    cron_jobs = home / "cron" / "jobs.json"
    ops_dir = home / "ops"
    config_path = openclaw_json if openclaw_json.exists() else openclaw_sub_json

    markers = {
        "openclaw_json": openclaw_json.exists() or openclaw_sub_json.exists(),
        "cron_jobs": cron_jobs.exists(),
        "ops_dir": ops_dir.is_dir(),
    }
    marker_score = sum(1 for val in markers.values() if val)
    valid = bool(markers["ops_dir"] and marker_score >= 2)

    mtime = 0.0
    if cron_jobs.exists():
        mtime = max(mtime, cron_jobs.stat().st_mtime)
    if config_path.exists():
        mtime = max(mtime, config_path.stat().st_mtime)
    if ops_dir.exists():
        mtime = max(mtime, ops_dir.stat().st_mtime)
    if mtime <= 0 and home.exists():
        mtime = home.stat().st_mtime

    return {
        "path": str(home),
        "exists": home.exists(),
        "source": source,
        "valid": valid,
        "marker_score": marker_score,
        "markers": markers,
        "version": parse_version_from_config(config_path),
        "jobs_file": str(cron_jobs),
        "jobs_count": read_jobs_count(cron_jobs),
        "last_modified_ts": mtime,
    }


def candidate_paths_from_env() -> list[tuple[Path, str]]:
    out: list[tuple[Path, str]] = []
    for key in ("OPENCLAW_HOME", "OPENCLAW_HOMES", "OPENCLAW_DIR"):
        for item in split_path_like(str(os.environ.get(key, "")).strip()):
            out.append((Path(item), f"env:{key}"))
    return out


def default_candidate_paths() -> list[tuple[Path, str]]:
    home = Path.home()
    out = [
        (home / ".openclaw", "default"),
        (home / ".config" / "openclaw", "default"),
    ]
    if os.name != "nt":
        out.extend(
            [
                (Path("/opt/openclaw"), "default"),
                (Path("/usr/local/openclaw"), "default"),
                (Path("/srv/openclaw"), "default"),
            ]
        )
    return out


def scan_for_openclaw_roots(
    roots: list[Path],
    max_depth: int,
    max_results: int,
) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        root_resolved = safe_resolve(root)
        for cur, dirs, _files in os.walk(root_resolved):
            cur_path = Path(cur)
            rel_depth = len(cur_path.relative_to(root_resolved).parts)
            if rel_depth > max_depth:
                dirs[:] = []
                continue

            dirs[:] = [d for d in dirs if d not in PRUNE_DIRS]
            name_hint = "openclaw" in cur_path.name.lower()
            marker_hint = (
                (cur_path / "ops").is_dir()
                and ((cur_path / "cron" / "jobs.json").exists() or (cur_path / "openclaw.json").exists())
            )
            if name_hint or marker_hint:
                found.append((cur_path, f"scan:{root_resolved}"))
                if len(found) >= max_results:
                    return found
    return found


def deduplicate_candidates(candidates: list[tuple[Path, str]]) -> list[tuple[Path, str]]:
    dedup: dict[str, tuple[Path, str]] = {}
    for path, source in candidates:
        key = str(safe_resolve(path))
        if key not in dedup:
            dedup[key] = (path, source)
        else:
            old_path, old_source = dedup[key]
            if old_source.startswith("default") and not source.startswith("default"):
                dedup[key] = (old_path, source)
    return sorted(dedup.values(), key=lambda x: str(safe_resolve(x[0])))


def choose_recommended(
    inspections: list[dict[str, Any]],
    prefer_path: str,
) -> dict[str, Any] | None:
    if not inspections:
        return None

    if prefer_path:
        prefer = str(safe_resolve(Path(prefer_path)))
        for item in inspections:
            if item.get("path") == prefer:
                return item

    env_home = str(os.environ.get("OPENCLAW_HOME", "")).strip()
    if env_home:
        resolved_env_home = str(safe_resolve(Path(env_home)))
        for item in inspections:
            if item.get("path") == resolved_env_home:
                return item

    ranked = sorted(
        inspections,
        key=lambda x: (
            bool(x.get("valid")),
            int(x.get("marker_score", 0)),
            float(x.get("last_modified_ts", 0.0)),
        ),
        reverse=True,
    )
    return ranked[0] if ranked else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect OpenClaw installations")
    parser.add_argument("--scan-root", action="append", default=[], help="extra scan roots (repeatable)")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--max-results", type=int, default=80)
    parser.add_argument("--prefer-path", default="", help="prefer this path if discovered")
    parser.add_argument("--skip-default-roots", action="store_true")
    parser.add_argument("--only-valid", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    candidates: list[tuple[Path, str]] = []
    candidates.extend(candidate_paths_from_env())
    if not args.skip_default_roots:
        candidates.extend(default_candidate_paths())

    scan_roots = [Path(x).expanduser() for x in args.scan_root if str(x).strip()]
    if scan_roots:
        candidates.extend(
            scan_for_openclaw_roots(
                roots=scan_roots,
                max_depth=max(1, int(args.max_depth)),
                max_results=max(1, int(args.max_results)),
            )
        )

    unique_candidates = deduplicate_candidates(candidates)
    inspections = [inspect_installation(path, source) for path, source in unique_candidates]
    if args.only_valid:
        inspections = [item for item in inspections if item.get("valid")]
    recommended = choose_recommended(inspections, prefer_path=str(args.prefer_path or "").strip())

    result = {
        "ok": True,
        "generated_at": now_iso(),
        "count": len(inspections),
        "valid_count": sum(1 for x in inspections if x.get("valid")),
        "recommended": recommended,
        "installations": inspections,
    }

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"generated_at={result['generated_at']}")
        print(f"count={result['count']}")
        print(f"valid_count={result['valid_count']}")
        if recommended:
            print(f"recommended={recommended.get('path')}")
        for item in inspections:
            ver = item.get("version") or "-"
            status = "valid" if item.get("valid") else "candidate"
            print(f"{item.get('path')} | {status} | v={ver} | source={item.get('source')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

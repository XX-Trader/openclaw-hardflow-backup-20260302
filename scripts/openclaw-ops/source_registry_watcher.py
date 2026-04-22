#!/usr/bin/env python3
"""
第三方来源注册表监控器。
定期检查项目声明的第三方依赖是否有更新。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def setup_logging() -> logging.Logger:
    log_dir = Path(".workflow/logs/source_registry_watcher")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

    logger = logging.getLogger("source_registry_watcher")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger


DATA_DIR = Path(".workflow/project-memory")
USER_AGENT = "OpenClaw-SourceWatcher/1.0"
REQUEST_TIMEOUT = 30


def fetch_url(url: str) -> Optional[str]:
    try:
        req = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (URLError, HTTPError, OSError) as err:
        logging.getLogger("source_registry_watcher").warning("获取失败 %s: %s", url, err)
        return None


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def load_registry(project_dir: Path) -> Optional[dict]:
    path = project_dir / "SOURCE_REGISTRY.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as err:
        logging.getLogger("source_registry_watcher").error("加载失败 %s: %s", path, err)
        return None


def check_source(source: dict) -> dict:
    name = source.get("source_id", "unknown")
    urls = source.get("urls", {})
    check_url = urls.get("changelog") or urls.get("docs") or urls.get("repo", "")
    last_hash = source.get("last_hash", "")

    result = {
        "source_id": name,
        "url": check_url,
        "status": "unknown",
        "changed": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    if not check_url:
        result["status"] = "no_url"
        return result

    content = fetch_url(check_url)
    if content is None:
        result["status"] = "fetch_failed"
        return result

    current_hash = compute_hash(content)
    result["current_hash"] = current_hash

    if last_hash and current_hash != last_hash:
        result["changed"] = True
        result["status"] = "changed"
        result["previous_hash"] = last_hash
    elif not last_hash:
        result["status"] = "first_check"
    else:
        result["status"] = "unchanged"

    return result


def update_registry(project_dir: Path, results: list[dict]) -> None:
    registry = load_registry(project_dir)
    if not registry:
        return

    sources = registry.get("sources", [])
    result_map = {r["source_id"]: r for r in results}

    for source in sources:
        sid = source.get("source_id", "")
        if sid in result_map:
            res = result_map[sid]
            if res.get("current_hash"):
                source["last_hash"] = res["current_hash"]
            source["last_checked"] = res.get("checked_at", "")

    path = project_dir / "SOURCE_REGISTRY.json"
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_changelog(project_dir: Path, changes: list[dict], project_key: str) -> None:
    path = project_dir / "CHANGELOG.ndjson"
    with open(path, "a", encoding="utf-8") as f:
        for change in changes:
            record = {
                "timestamp": change.get("checked_at", datetime.now(timezone.utc).isoformat()),
                "project_key": project_key,
                "source_id": change["source_id"],
                "change_type": "source_changed",
                "summary": f"来源 [{change['source_id']}] 内容已变更",
                "details": {
                    "url": change.get("url", ""),
                    "previous_hash": change.get("previous_hash", ""),
                    "current_hash": change.get("current_hash", ""),
                },
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def check_project(project_key: str) -> dict:
    project_dir = DATA_DIR / project_key
    if not project_dir.exists():
        return {"error": "project_not_found", "project_key": project_key}

    registry = load_registry(project_dir)
    if not registry:
        return {"project_key": project_key, "skipped": "no_registry"}

    sources = registry.get("sources", [])
    if not sources:
        return {"project_key": project_key, "skipped": "empty_registry"}

    results = [check_source(s) for s in sources]
    update_registry(project_dir, results)

    changes = [r for r in results if r.get("changed")]
    if changes:
        append_changelog(project_dir, changes, project_key)

    return {
        "project_key": project_key,
        "total_sources": len(sources),
        "checked": len(results),
        "changed": len(changes),
        "failed": len([r for r in results if r["status"] == "fetch_failed"]),
        "details": results,
    }


def check_all() -> list[dict]:
    if not DATA_DIR.exists():
        return []

    projects = sorted([d.name for d in DATA_DIR.iterdir() if d.is_dir()])
    return [check_project(p) for p in projects]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="第三方来源注册表监控器")
    parser.add_argument("--project-key", help="检查指定项目")
    parser.add_argument("--scan-all", action="store_true", help="检查所有项目")
    parser.add_argument("--base-path", default=str(DATA_DIR), help="项目记忆根目录")
    parser.add_argument("--notify-on-change", action="store_true")
    args = parser.parse_args(argv)

    logger = setup_logging()

    if args.scan_all:
        results = check_all()
        changed_count = sum(r.get("changed", 0) for r in results)
        logger.info("扫描完成: %d 个项目, %d 个变更", len(results), changed_count)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if changed_count == 0 else 1

    if args.project_key:
        result = check_project(args.project_key)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("changed", 0) == 0 else 1

    print(json.dumps({"error": "missing_arguments"}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

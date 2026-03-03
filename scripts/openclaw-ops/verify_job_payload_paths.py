#!/usr/bin/env python3
"""Verify script and file paths referenced by OpenClaw cron jobs payload commands."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
FILE_FLAGS = {
    "--config",
    "--config-file",
    "--state-file",
    "--db",
    "--registry",
    "--env-file",
}
DIR_FLAGS = {
    "--history-dir",
    "--report-dir",
    "--output-dir",
    "--workspace",
}
OPTIONAL_FILE_FLAGS = {"--state-file"}
OPTIONAL_DIR_FLAGS = {"--history-dir", "--report-dir", "--output-dir"}


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def extract_command_from_message(message: str) -> str:
    text = str(message or "").strip()
    if not text:
        return ""

    # English template (preferred)
    m = re.search(r"Run command only:\s*(.+?)(?:\n(?:Reply|Do not)|$)", text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        return str(m.group(1)).strip()

    # Chinese template variants
    for marker in ("参数：", "只执行以下命令", "仅用命令执行"):
        if marker in text:
            part = text.split(marker, 1)[1].lstrip("：: \n")
            end_idx = len(part)
            for stop in ("\n", "。", "；"):
                idx = part.find(stop)
                if idx >= 0:
                    end_idx = min(end_idx, idx)
            return part[:end_idx].strip()

    # Generic fallback: first command-looking line.
    m = re.search(r"((?:python|python3|bash|sh|node)\s+[^\n]+)", text, flags=re.IGNORECASE)
    if m:
        return str(m.group(1)).strip()
    return ""


def resolve_path(raw: str, cwd: Path) -> Path:
    expanded = os.path.expandvars(str(raw or ""))
    p = Path(expanded).expanduser()
    if p.is_absolute():
        return p
    return (cwd / p).resolve()


def parse_references(command: str, cwd: Path) -> dict[str, Any]:
    refs = {"script_path": "", "file_flags": [], "dir_flags": []}
    if not command:
        return refs
    try:
        parts = shlex.split(command, posix=True)
    except Exception:
        parts = command.split()
    if not parts:
        return refs

    first = str(parts[0]).strip().lower()
    # python3 script.py ...
    if first.startswith("python") and len(parts) >= 2:
        refs["script_path"] = str(resolve_path(parts[1], cwd))
    # bash script.sh / node script.mjs
    elif first in {"bash", "sh", "node"} and len(parts) >= 2:
        refs["script_path"] = str(resolve_path(parts[1], cwd))
    # /usr/bin/env bash script.sh ...
    elif first.endswith("/env") and len(parts) >= 3 and str(parts[1]).strip().lower() in {"python", "python3", "bash", "sh", "node"}:
        refs["script_path"] = str(resolve_path(parts[2], cwd))

    idx = 0
    while idx < len(parts):
        token = parts[idx]
        if token in FILE_FLAGS and (idx + 1) < len(parts):
            refs["file_flags"].append({"flag": token, "path": str(resolve_path(parts[idx + 1], cwd))})
            idx += 2
            continue
        if token in DIR_FLAGS and (idx + 1) < len(parts):
            refs["dir_flags"].append({"flag": token, "path": str(resolve_path(parts[idx + 1], cwd))})
            idx += 2
            continue
        idx += 1
    return refs


def check_paths(job: dict[str, Any], cwd: Path, require_parse: bool) -> dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    message = str(payload.get("message", "") or "")
    command = extract_command_from_message(message)
    refs = parse_references(command, cwd=cwd)
    issues: list[str] = []
    checks: list[dict[str, Any]] = []

    script_path = str(refs.get("script_path", "")).strip()
    if script_path:
        sp = Path(script_path)
        ok = sp.exists() and sp.is_file()
        checks.append({"type": "script", "path": str(sp), "exists": ok})
        if not ok:
            issues.append(f"script_missing:{sp}")
    else:
        checks.append({"type": "script", "path": "", "exists": False, "parsed": False})
        if require_parse:
            issues.append("script_not_parsed")

    for item in refs.get("file_flags", []):
        p = Path(item["path"])
        ok = p.exists()
        required = item["flag"] not in OPTIONAL_FILE_FLAGS
        checks.append({"type": "file", "flag": item["flag"], "path": str(p), "exists": ok, "required": required})
        if required and not ok:
            issues.append(f"file_missing:{item['flag']}:{p}")
    for item in refs.get("dir_flags", []):
        p = Path(item["path"])
        ok = p.exists() and p.is_dir()
        required = item["flag"] not in OPTIONAL_DIR_FLAGS
        checks.append({"type": "dir", "flag": item["flag"], "path": str(p), "exists": ok, "required": required})
        if required and not ok:
            issues.append(f"dir_missing:{item['flag']}:{p}")

    return {
        "id": str(job.get("id", "")).strip(),
        "name": str(job.get("name", "")).strip(),
        "command": command,
        "checks": checks,
        "issues": issues,
        "ok": len(issues) == 0,
    }


def main() -> int:
    home = Path(os.path.expanduser("~"))
    parser = argparse.ArgumentParser(description="Verify cron job payload paths")
    parser.add_argument("--jobs-file", default=str(home / ".openclaw/cron/jobs.json"))
    parser.add_argument("--job-name", action="append", default=[], help="limit to specific job names")
    parser.add_argument("--require-parse", action="store_true", help="treat unparsed payload commands as issues")
    parser.add_argument("--strict", action="store_true", help="non-zero exit on any issue")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    jobs_file = Path(args.jobs_file).expanduser()
    if not jobs_file.exists():
        payload = {"ok": False, "error": f"jobs file missing: {jobs_file}"}
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    data = json.loads(jobs_file.read_text(encoding="utf-8-sig"))
    jobs = data.get("jobs", []) if isinstance(data, dict) and isinstance(data.get("jobs"), list) else []

    wanted = {str(x).strip() for x in args.job_name if str(x).strip()}
    if wanted:
        jobs = [x for x in jobs if isinstance(x, dict) and str(x.get("name", "")).strip() in wanted]

    cwd = jobs_file.parent.parent if jobs_file.parent.name == "cron" else jobs_file.parent
    entries = [check_paths(job, cwd=cwd, require_parse=bool(args.require_parse)) for job in jobs if isinstance(job, dict)]
    issue_count = sum(len(x.get("issues", [])) for x in entries)
    result = {
        "ok": issue_count == 0,
        "generated_at": now_iso(),
        "jobs_file": str(jobs_file),
        "job_count": len(entries),
        "issue_count": issue_count,
        "entries": entries,
    }

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"jobs_file={result['jobs_file']}")
        print(f"job_count={result['job_count']}")
        print(f"issue_count={result['issue_count']}")
        for item in entries:
            status = "ok" if item.get("ok") else "bad"
            print(f"{item.get('name')}={status}")
    if args.strict and issue_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

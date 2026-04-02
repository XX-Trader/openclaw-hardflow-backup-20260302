#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


DEFAULT_AUTO_EXCLUDE_SERVERS = {"google-us"}
DEFAULT_REPO_CANDIDATES = (
    "~/openclaw-hardflow-backup-20260302",
    "~/projects/openclaw-hardflow-backup-20260302",
)
DEFAULT_VOLATILE_PREFIXES = (
    ".workflow/project-index/",
    ".workflow/project-index-local/",
    ".workflow/experience/",
    ".workflow/sessions/",
    "scripts/openclaw-ops/policy/runtime/",
    "openclaw-memory/",
    "memory/",
)
DEFAULT_STRATEGY = "runtime-reset"
CONFLICT_STRATEGIES = ("runtime-reset", "stash-nonvolatile", "snapshot-branch")


def detect_default_ssh_config() -> str:
    candidates = [
        os.environ.get("SSH_CONFIG", ""),
        "D:/ssh_keys/ssh_config",
        "/d/ssh_keys/ssh_config",
        "/mnt/d/ssh_keys/ssh_config",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return ""


def detect_ssh_binary() -> str:
    return shutil.which("ssh.exe") or shutil.which("ssh") or "ssh"


def parse_ssh_hosts(text: str) -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or not line.lower().startswith("host "):
            continue
        for token in line.split()[1:]:
            value = str(token or "").strip()
            if not value or any(ch in value for ch in ("*", "?", "!")):
                continue
            if value not in seen:
                seen.add(value)
                hosts.append(value)
    return hosts


def load_servers_from_ssh_config(ssh_config: str, *, auto_exclude: Iterable[str]) -> list[str]:
    excluded = {str(item).strip() for item in auto_exclude if str(item).strip()}
    content = Path(ssh_config).read_text(encoding="utf-8", errors="replace")
    return [host for host in parse_ssh_hosts(content) if host not in excluded]


def normalize_rel_path(value: str) -> str:
    normalized = str(value or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def parse_porcelain_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip("\n")
        if len(line) < 3:
            continue
        status = line[:2]
        raw_path = line[3:].strip()
        if not raw_path:
            continue
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        path = normalize_rel_path(raw_path)
        if path:
            entries.append({"status": status, "path": path})
    return entries


def unique_preserve(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "")
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def is_volatile_path(path: str, prefixes: Iterable[str]) -> bool:
    normalized = normalize_rel_path(path)
    for raw_prefix in prefixes:
        prefix = normalize_rel_path(raw_prefix).rstrip("/")
        if not prefix:
            continue
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def split_dirty_paths(entries: Iterable[dict[str, str]], prefixes: Iterable[str]) -> tuple[list[str], list[str]]:
    volatile: list[str] = []
    blocking: list[str] = []
    for entry in entries:
        path = normalize_rel_path(entry.get("path", ""))
        if not path:
            continue
        if is_volatile_path(path, prefixes):
            volatile.append(path)
        else:
            blocking.append(path)
    return unique_preserve(volatile), unique_preserve(blocking)


def build_remote_script(
    *,
    mode: str,
    repo_candidates: list[str],
    volatile_prefixes: list[str],
    branch: str,
    remote_name: str,
    strategy: str,
) -> str:
    config_json = json.dumps(
        {
            "mode": mode,
            "repo_candidates": repo_candidates,
            "volatile_prefixes": [normalize_rel_path(item) for item in volatile_prefixes],
            "branch": branch,
            "remote_name": remote_name,
            "strategy": strategy,
        },
        ensure_ascii=False,
    )
    return f"""
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

CONFIG = json.loads({config_json!r})


def normalize_rel_path(value):
    normalized = str(value or "").replace("\\\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def unique_preserve(items):
    result = []
    seen = set()
    for item in items:
        value = str(item or "")
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def parse_porcelain_entries(text):
    entries = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip("\\n")
        if len(line) < 3:
            continue
        status = line[:2]
        raw_path = line[3:].strip()
        if not raw_path:
            continue
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        path = normalize_rel_path(raw_path)
        if path:
            entries.append({{"status": status, "path": path}})
    return entries


def is_volatile_path(path):
    normalized = normalize_rel_path(path)
    for raw_prefix in CONFIG["volatile_prefixes"]:
        prefix = normalize_rel_path(raw_prefix).rstrip("/")
        if not prefix:
            continue
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def run(args, cwd):
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, str(proc.stdout or ""), str(proc.stderr or "")


def resolve_candidates():
    found = []
    for raw_path in CONFIG["repo_candidates"]:
        expanded = Path(raw_path).expanduser()
        if (expanded / ".git").exists():
            found.append(str(expanded))
    return unique_preserve(found)


def append_error(result, *parts):
    for part in parts:
        value = str(part or "").strip()
        if value:
            result["errors"].append(value)


def refresh_dirty_state(result, repo):
    rc, out, err = run(["git", "status", "--porcelain=v1", "--untracked-files=all"], repo)
    if rc != 0:
        append_error(result, err)
        result["status"] = "git_status_failed"
        return False
    entries = parse_porcelain_entries(out)
    result["dirty_entries"] = entries
    result["volatile_dirty"] = unique_preserve(
        entry["path"] for entry in entries if is_volatile_path(entry["path"])
    )
    result["blocking_dirty"] = unique_preserve(
        entry["path"] for entry in entries if not is_volatile_path(entry["path"])
    )
    return True


result = {{
    "mode": CONFIG["mode"],
    "strategy": CONFIG["strategy"],
    "status": "unknown",
    "repo_candidates": resolve_candidates(),
    "repo_path": "",
    "branch": "",
    "remote_url": "",
    "head_before": "",
    "head_after": "",
    "ahead": 0,
    "behind": 0,
    "dirty_entries": [],
    "volatile_dirty": [],
    "blocking_dirty": [],
    "actions": [],
    "errors": [],
    "stash_created": False,
    "stash_message": "",
    "snapshot_branch": "",
}}

if shutil.which("git") is None:
    result["status"] = "git_missing"
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

if not result["repo_candidates"]:
    result["status"] = "missing_repo"
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

if len(result["repo_candidates"]) > 1:
    result["status"] = "ambiguous_repo"
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

repo = Path(result["repo_candidates"][0])
result["repo_path"] = str(repo)

rc, out, err = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
if rc != 0:
    result["status"] = "git_status_failed"
    append_error(result, err)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)
result["branch"] = out.strip()

rc, out, err = run(["git", "remote", "get-url", CONFIG["remote_name"]], repo)
if rc == 0:
    result["remote_url"] = out.strip()

rc, out, err = run(["git", "rev-parse", "--short", "HEAD"], repo)
if rc == 0:
    result["head_before"] = out.strip()

if not refresh_dirty_state(result, repo):
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

rc, out, err = run(["git", "fetch", CONFIG["remote_name"], CONFIG["branch"]], repo)
if rc != 0:
    result["status"] = "fetch_failed"
    append_error(result, err)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)
result["actions"].append(f"git fetch {{CONFIG['remote_name']}} {{CONFIG['branch']}}")

rc, out, err = run(
    ["git", "rev-list", "--left-right", "--count", f"HEAD...{{CONFIG['remote_name']}}/{{CONFIG['branch']}}"],
    repo,
)
if rc == 0:
    parts = out.strip().split()
    if len(parts) >= 2:
        try:
            result["ahead"] = int(parts[0])
            result["behind"] = int(parts[1])
        except ValueError:
            append_error(result, f"invalid_ahead_behind={{out.strip()}}")

if CONFIG["mode"] == "inspect":
    result["status"] = "inspect_ok"
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

if result["branch"] != CONFIG["branch"]:
    result["status"] = "blocked_branch"
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

if result["ahead"] > 0 and result["behind"] > 0:
    result["status"] = "blocked_diverged"
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

if result["ahead"] > 0:
    result["status"] = "blocked_local_commits"
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

strategy = CONFIG["strategy"]
if strategy == "runtime-reset":
    if result["blocking_dirty"]:
        result["status"] = "blocked_dirty_nonvolatile"
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0)
elif strategy == "stash-nonvolatile":
    if result["blocking_dirty"]:
        stash_message = "remote-safe-update:" + datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        rc, out, err = run(
            ["git", "stash", "push", "--include-untracked", "-m", stash_message, "--", *result["blocking_dirty"]],
            repo,
        )
        if rc != 0:
            result["status"] = "stash_failed"
            append_error(result, err)
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0)
        result["stash_created"] = True
        result["stash_message"] = stash_message
        result["actions"].append("git stash push blocking paths")
        if not refresh_dirty_state(result, repo):
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0)
elif strategy == "snapshot-branch":
    if result["blocking_dirty"]:
        snapshot_branch = "ops/autosave-before-sync-" + datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        rc, out, err = run(["git", "switch", "-c", snapshot_branch], repo)
        if rc != 0:
            result["status"] = "snapshot_branch_failed"
            append_error(result, err)
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0)
        rc, out, err = run(["git", "add", "-A"], repo)
        if rc != 0:
            result["status"] = "snapshot_add_failed"
            append_error(result, err)
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0)
        rc, out, err = run(["git", "commit", "-m", f"chore: autosave before remote-safe-update"], repo)
        if rc != 0:
            result["status"] = "snapshot_commit_failed"
            append_error(result, out, err)
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0)
        rc, out, err = run(["git", "switch", CONFIG["branch"]], repo)
        if rc != 0:
            result["status"] = "snapshot_return_failed"
            append_error(result, err)
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0)
        result["snapshot_branch"] = snapshot_branch
        result["actions"].append(f"snapshot branch {{snapshot_branch}}")
        if not refresh_dirty_state(result, repo):
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(0)
else:
    result["status"] = "unknown_strategy"
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)

tracked_volatile = unique_preserve(
    entry["path"]
    for entry in result["dirty_entries"]
    if is_volatile_path(entry["path"]) and entry.get("status") != "??"
)
if tracked_volatile:
    rc, out, err = run(["git", "restore", "--source=HEAD", "--staged", "--worktree", "--", *tracked_volatile], repo)
    if rc != 0:
        result["status"] = "volatile_restore_failed"
        append_error(result, err)
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0)
    result["actions"].append(f"git restore volatile tracked: {{len(tracked_volatile)}}")

if CONFIG["volatile_prefixes"]:
    rc, out, err = run(["git", "clean", "-fd", "--", *CONFIG["volatile_prefixes"]], repo)
    if rc != 0:
        result["status"] = "volatile_clean_failed"
        append_error(result, err)
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0)
    result["actions"].append("git clean volatile prefixes")

rc, out, err = run(["git", "pull", "--ff-only", CONFIG["remote_name"], CONFIG["branch"]], repo)
if rc != 0:
    result["status"] = "pull_failed"
    append_error(result, err)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0)
result["actions"].append(f"git pull --ff-only {{CONFIG['remote_name']}} {{CONFIG['branch']}}")

if strategy == "stash-nonvolatile" and result["stash_created"]:
    rc, out, err = run(["git", "stash", "pop"], repo)
    if rc != 0:
        result["status"] = "stash_pop_conflict"
        append_error(result, out, err)
        if refresh_dirty_state(result, repo):
            pass
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0)
    result["actions"].append("git stash pop")

rc, out, err = run(["git", "rev-parse", "--short", "HEAD"], repo)
if rc == 0:
    result["head_after"] = out.strip()

refresh_dirty_state(result, repo)
result["status"] = "sync_complete"
print(json.dumps(result, ensure_ascii=False))
"""


def run_remote_script(
    *,
    server: str,
    ssh_bin: str,
    ssh_config: str,
    remote_script: str,
    timeout_seconds: int,
    connect_timeout: int,
) -> dict[str, object]:
    proc = subprocess.run(
        [
            ssh_bin,
            "-F",
            ssh_config,
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={max(1, int(connect_timeout))}",
            "-o",
            "StrictHostKeyChecking=accept-new",
            server,
            "python3 -",
        ],
        input=remote_script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(30, int(timeout_seconds)),
    )
    stdout = str(proc.stdout or "").strip()
    stderr = str(proc.stderr or "").strip()
    if proc.returncode != 0:
        return {
            "server": server,
            "status": "ssh_failed",
            "errors": [part for part in (stdout, stderr) if part],
        }
    if not stdout:
        return {
            "server": server,
            "status": "empty_response",
            "errors": [stderr] if stderr else [],
        }
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "server": server,
            "status": "invalid_json",
            "errors": [stdout, stderr],
        }
    if not isinstance(payload, dict):
        payload = {"status": "invalid_payload", "errors": [repr(payload)]}
    payload["server"] = server
    return payload


def summarize_statuses(results: Iterable[dict[str, object]]) -> dict[str, int]:
    summary = {
        "total": 0,
        "inspect_ok": 0,
        "sync_complete": 0,
        "blocked": 0,
        "errors": 0,
    }
    for item in results:
        summary["total"] += 1
        status = str(item.get("status", ""))
        if status == "inspect_ok":
            summary["inspect_ok"] += 1
        elif status == "sync_complete":
            summary["sync_complete"] += 1
        elif status.startswith("blocked_") or status in {"ambiguous_repo", "missing_repo", "stash_pop_conflict"}:
            summary["blocked"] += 1
        else:
            summary["errors"] += 1
    return summary


def render_human_report(results: list[dict[str, object]], *, mode: str, strategy: str) -> str:
    lines = [f"# remote-safe-update mode={mode} strategy={strategy}"]
    for item in results:
        server = str(item.get("server", ""))
        status = str(item.get("status", ""))
        branch = str(item.get("branch", "") or "-")
        repo_path = str(item.get("repo_path", "") or "-")
        ahead = int(item.get("ahead", 0) or 0)
        behind = int(item.get("behind", 0) or 0)
        lines.append(f"- server={server} status={status} branch={branch} ahead={ahead} behind={behind} repo={repo_path}")
        volatile_dirty = [str(v) for v in (item.get("volatile_dirty") or []) if str(v).strip()]
        blocking_dirty = [str(v) for v in (item.get("blocking_dirty") or []) if str(v).strip()]
        actions = [str(v) for v in (item.get("actions") or []) if str(v).strip()]
        if volatile_dirty:
            lines.append(f"  volatile_dirty={', '.join(volatile_dirty[:8])}")
        if blocking_dirty:
            lines.append(f"  blocking_dirty={', '.join(blocking_dirty[:8])}")
        if actions:
            lines.append(f"  actions={'; '.join(actions)}")
        if item.get("stash_created"):
            lines.append(f"  stash_message={item.get('stash_message')}")
        if item.get("snapshot_branch"):
            lines.append(f"  snapshot_branch={item.get('snapshot_branch')}")
        errors = [str(v) for v in (item.get("errors") or []) if str(v).strip()]
        if errors:
            lines.append(f"  errors={errors[0]}")
    summary = summarize_statuses(results)
    lines.append("summary: " + " ".join(f"{k}={v}" for k, v in summary.items()))
    return "\n".join(lines)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or sync remote OpenClaw workflow repositories with explicit conflict strategies. "
            "Default behavior only resets volatile runtime files and blocks on other changes."
        )
    )
    parser.add_argument("--mode", choices=("inspect", "sync"), default="inspect")
    parser.add_argument("--strategy", choices=CONFLICT_STRATEGIES, default=DEFAULT_STRATEGY)
    parser.add_argument("--ssh-config", default=detect_default_ssh_config())
    parser.add_argument("--ssh-bin", default=detect_ssh_binary())
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--connect-timeout", type=int, default=15)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    parser.add_argument("--servers", nargs="*", default=[])
    parser.add_argument("--repo-path", default="")
    parser.add_argument("--repo-candidate", action="append", dest="repo_candidates")
    parser.add_argument("--volatile-prefix", action="append", dest="volatile_prefixes")
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    ssh_config = str(args.ssh_config or "").strip()
    if not ssh_config:
        parser.error("--ssh-config is required when SSH_CONFIG cannot be auto-detected")
    if not Path(ssh_config).exists():
        parser.error(f"ssh_config not found: {ssh_config}")

    if args.servers:
        servers = [str(item).strip() for item in args.servers if str(item).strip()]
    else:
        servers = load_servers_from_ssh_config(ssh_config, auto_exclude=DEFAULT_AUTO_EXCLUDE_SERVERS)
    if not servers:
        parser.error("no servers resolved")

    if str(args.repo_path or "").strip():
        repo_candidates = [str(args.repo_path).strip()]
    else:
        repo_candidates = list(args.repo_candidates or DEFAULT_REPO_CANDIDATES)
    volatile_prefixes = list(args.volatile_prefixes or DEFAULT_VOLATILE_PREFIXES)

    remote_script = build_remote_script(
        mode=str(args.mode),
        repo_candidates=repo_candidates,
        volatile_prefixes=volatile_prefixes,
        branch=str(args.branch),
        remote_name=str(args.remote),
        strategy=str(args.strategy),
    )
    results = [
        run_remote_script(
            server=server,
            ssh_bin=str(args.ssh_bin),
            ssh_config=ssh_config,
            remote_script=remote_script,
            timeout_seconds=int(args.timeout_seconds),
            connect_timeout=int(args.connect_timeout),
        )
        for server in servers
    ]
    payload = {
        "mode": args.mode,
        "strategy": args.strategy,
        "ssh_config": ssh_config,
        "servers": servers,
        "repo_candidates": repo_candidates,
        "volatile_prefixes": volatile_prefixes,
        "results": results,
        "summary": summarize_statuses(results),
    }
    if args.emit_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_human_report(results, mode=str(args.mode), strategy=str(args.strategy)))

    summary = summarize_statuses(results)
    if summary["errors"] > 0:
        return 2
    if args.mode == "sync" and summary["blocked"] > 0:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Ensure required OpenClaw runtime skills and command dependencies exist."""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_PROFILE_LINES = (
    'export PATH="$HOME/.npm-global/bin:$PATH"',
)


def load_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"json root must be an object: {path}")
    return raw


def run_cmd(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = 600,
) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return int(proc.returncode), (proc.stdout or "").strip(), (proc.stderr or "").strip()


def remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def verify_skill_dir(path: Path) -> bool:
    return (path / "SKILL.md").exists()


def safe_extract_tar(tar: tarfile.TarFile, target_dir: Path) -> None:
    base = target_dir.resolve()
    for member in tar.getmembers():
        member_path = (target_dir / member.name).resolve()
        if os.path.commonpath([str(base), str(member_path)]) != str(base):
            raise RuntimeError(f"unsafe archive entry: {member.name}")
    tar.extractall(path=target_dir)


def expand_target_dir(openclaw_home: Path, target: str) -> Path:
    normalized = str(target or "").strip().lower()
    if normalized == "managed":
        return openclaw_home / "skills"
    if normalized == "workspace":
        return openclaw_home / "workspace" / "skills"
    raise ValueError(f"unsupported skill target: {target}")


def resolve_skill_target_dirs(openclaw_home: Path, entry: dict[str, Any]) -> list[Path]:
    install = entry.get("install") if isinstance(entry.get("install"), dict) else {}
    raw_targets = install.get("targets")
    targets = raw_targets if isinstance(raw_targets, list) and raw_targets else ["managed", "workspace"]
    resolved: list[Path] = []
    seen: set[str] = set()
    for item in targets:
        path = expand_target_dir(openclaw_home, str(item))
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        resolved.append(path)
    return resolved


def prepare_skill_source(entry: dict[str, Any], work_dir: Path) -> tuple[Path, str]:
    install = entry.get("install") if isinstance(entry.get("install"), dict) else {}
    source_dir_text = str(install.get("source_dir") or "").strip()
    if source_dir_text:
        source_dir = Path(source_dir_text).expanduser().resolve()
        if not verify_skill_dir(source_dir):
            raise RuntimeError(f"skill source missing SKILL.md: {source_dir}")
        return source_dir, "source-dir"

    repo_url = str(install.get("repo_url") or "").strip()
    archive_url = str(install.get("archive_url") or "").strip()
    clone_dir = work_dir / "skill-src"
    if repo_url and shutil.which("git"):
        rc, _out, err = run_cmd(["git", "clone", "--depth", "1", repo_url, str(clone_dir)], timeout=900)
        if rc == 0 and verify_skill_dir(clone_dir):
            return clone_dir, "git"
        remove_path(clone_dir)
        if not archive_url:
            raise RuntimeError(f"git clone failed: {err or repo_url}")

    if archive_url:
        clone_dir.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(archive_url, timeout=120) as resp:
            data = resp.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            safe_extract_tar(tar, clone_dir)
        extracted = [p for p in clone_dir.iterdir() if p.is_dir()]
        source_root = extracted[0] if len(extracted) == 1 and verify_skill_dir(extracted[0]) else clone_dir
        if verify_skill_dir(source_root):
            return source_root, "archive"
    raise RuntimeError(f"unable to prepare skill source for {entry.get('name')}")


def copy_skill_tree(source_dir: Path, target_dir: Path) -> None:
    if target_dir.exists():
        remove_path(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir, ignore=shutil.ignore_patterns(".git"))


def ensure_profile_line(profile_path: Path, line: str) -> bool:
    existing = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    lines = existing.splitlines()
    if line in lines:
        return False
    content = existing
    if content and not content.endswith("\n"):
        content += "\n"
    content += line + "\n"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(content, encoding="utf-8")
    return True


def command_candidates(command: str, npm_prefix: str = "") -> list[Path]:
    home = Path.home()
    out = [
        home / ".npm-global" / "bin" / command,
        home / ".local" / "bin" / command,
    ]
    prefix = str(npm_prefix or "").strip()
    if prefix:
        out.insert(0, Path(prefix) / "bin" / command)
    return out


def resolve_command_path(command: str, npm_prefix: str = "") -> str:
    direct = shutil.which(command)
    if direct:
        return direct
    for candidate in command_candidates(command, npm_prefix=npm_prefix):
        if candidate.exists() and candidate.is_file():
            return str(candidate)
    return ""


def verify_command(path_or_name: str, verify_args: list[str]) -> tuple[bool, str]:
    candidate = str(path_or_name or "").strip()
    if not candidate:
        return False, "missing-command"
    cmd = [candidate, *(verify_args or ["--version"])]
    try:
        rc, out, err = run_cmd(cmd, timeout=60)
    except Exception as exc:
        return False, str(exc)
    return rc == 0, out or err


def maybe_create_usr_local_symlink(command: str, candidate_path: str) -> tuple[bool, str]:
    if os.name == "nt":
        return False, ""
    dest = Path("/usr/local/bin") / command
    source = Path(candidate_path)
    if str(source) == str(dest):
        return False, str(dest)
    if dest.exists() or dest.is_symlink():
        return False, str(dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(source)
        return True, str(dest)
    except Exception:
        return False, str(dest)


def ensure_skill_entry(entry: dict[str, Any], openclaw_home: Path, dry_run: bool) -> dict[str, Any]:
    name = str(entry.get("name") or "").strip()
    conflicts = [str(x).strip() for x in (entry.get("conflicts") or []) if str(x).strip()]
    targets = resolve_skill_target_dirs(openclaw_home, entry)
    result: dict[str, Any] = {
        "name": name,
        "ok": True,
        "dry_run": dry_run,
        "changed": False,
        "conflicts": list(conflicts),
        "conflicts_removed": [],
        "targets": [],
        "install_method": "",
    }

    missing_targets: list[Path] = []
    for parent_dir in targets:
        target_dir = parent_dir / name
        removed_here: list[str] = []
        for conflict in conflicts:
            conflict_dir = parent_dir / conflict
            if conflict_dir.exists() or conflict_dir.is_symlink():
                removed_here.append(str(conflict_dir))
                if not dry_run:
                    remove_path(conflict_dir)
        if removed_here:
            result["changed"] = True
            result["conflicts_removed"].extend(removed_here)

        present = verify_skill_dir(target_dir)
        if not present:
            missing_targets.append(target_dir)
        result["targets"].append(
            {
                "parent_dir": str(parent_dir),
                "target_dir": str(target_dir),
                "present_before": present,
                "present_after": present if dry_run else verify_skill_dir(target_dir),
                "installed": False,
            }
        )

    if missing_targets and not dry_run:
        with tempfile.TemporaryDirectory(prefix="openclaw-skill-") as tmpdir:
            source_dir, method = prepare_skill_source(entry, Path(tmpdir))
            for target_dir in missing_targets:
                copy_skill_tree(source_dir, target_dir)
            result["install_method"] = method
        result["changed"] = True
    elif missing_targets:
        result["changed"] = True

    final_targets: list[dict[str, Any]] = []
    for item in result["targets"]:
        target_dir = Path(item["target_dir"])
        present_after = bool(item["present_before"]) if dry_run else verify_skill_dir(target_dir)
        item["present_after"] = present_after
        item["installed"] = (not item["present_before"]) and present_after and (not dry_run)
        item["would_install"] = (not item["present_before"]) and dry_run
        final_targets.append(item)

    result["targets"] = final_targets
    if any(not bool(item["present_after"]) for item in final_targets) and not dry_run:
        result["ok"] = False
        result["error"] = f"skill_missing_after_install:{name}"
    return result


def ensure_command_entry(entry: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    install = entry.get("install") if isinstance(entry.get("install"), dict) else {}
    name = str(entry.get("name") or "").strip()
    command = str(install.get("command") or name or "").strip()
    npm_package = str(install.get("npm_package") or "").strip()
    verify_args = [str(x).strip() for x in (install.get("verify_args") or ["--version"]) if str(x).strip()]
    result: dict[str, Any] = {
        "name": name,
        "command": command,
        "ok": True,
        "dry_run": dry_run,
        "changed": False,
        "present_before": False,
        "present_after": False,
        "resolved_path": "",
        "install_method": "",
        "profile_updates": [],
        "symlink_path": "",
    }

    prefix = ""
    path_before = resolve_command_path(command)
    verified_before, verify_before_output = verify_command(path_before or command, verify_args) if path_before else (False, "")
    result["present_before"] = bool(path_before) and verified_before
    if result["present_before"]:
        result["present_after"] = True
        result["resolved_path"] = path_before
        result["verify_output"] = verify_before_output
        return result

    if dry_run:
        result["changed"] = not result["present_before"]
        result["would_install"] = bool(npm_package)
        return result

    npm_bin = shutil.which("npm")
    if not npm_bin:
        result["ok"] = False
        result["error"] = "npm_not_found"
        return result

    rc, out, err = run_cmd([npm_bin, "i", "-g", npm_package], timeout=1800)
    if rc == 0:
        result["install_method"] = "npm-global"
        result["changed"] = True
    else:
        prefix_path = str(Path.home() / ".npm-global")
        rc_prefix, _out_prefix, err_prefix = run_cmd([npm_bin, "config", "set", "prefix", prefix_path], timeout=120)
        if rc_prefix != 0:
            result["ok"] = False
            result["error"] = err_prefix or "npm_prefix_config_failed"
            result["install_stdout"] = out
            result["install_stderr"] = err
            return result
        env = dict(os.environ)
        env["PATH"] = str(Path(prefix_path) / "bin") + os.pathsep + env.get("PATH", "")
        rc_user, out_user, err_user = run_cmd([npm_bin, "i", "-g", npm_package], env=env, timeout=1800)
        if rc_user != 0:
            result["ok"] = False
            result["error"] = err_user or "npm_user_install_failed"
            result["install_stdout"] = out_user or out
            result["install_stderr"] = err_user or err
            return result
        prefix = prefix_path
        result["install_method"] = "npm-user"
        result["changed"] = True
        for profile_name in (".bashrc", ".profile", ".zprofile"):
            profile_path = Path.home() / profile_name
            for line in DEFAULT_PROFILE_LINES:
                if ensure_profile_line(profile_path, line):
                    result["profile_updates"].append(str(profile_path))

    path_after = resolve_command_path(command, npm_prefix=prefix)
    verified_after, verify_after_output = verify_command(path_after or command, verify_args) if path_after else (False, "")
    if path_after and verified_after:
        result["present_after"] = True
        result["resolved_path"] = path_after
        result["verify_output"] = verify_after_output
        linked, symlink_path = maybe_create_usr_local_symlink(command, path_after)
        if linked:
            result["symlink_path"] = symlink_path
            result["resolved_path"] = symlink_path
    else:
        result["ok"] = False
        result["error"] = f"command_missing_after_install:{command}"
        result["verify_output"] = verify_after_output
    return result


def ensure_runtime_skills(manifest_path: Path, openclaw_home: Path, dry_run: bool) -> dict[str, Any]:
    manifest = load_json_object(manifest_path)
    skill_entries = manifest.get("skills") if isinstance(manifest.get("skills"), list) else []
    command_entries = manifest.get("commands") if isinstance(manifest.get("commands"), list) else []

    result: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "manifest": str(manifest_path.resolve()),
        "schema_version": str(manifest.get("schema_version") or ""),
        "openclaw_home": str(openclaw_home.resolve()),
        "skills": [],
        "commands": [],
        "changed": False,
    }

    for raw_entry in skill_entries:
        if not isinstance(raw_entry, dict):
            continue
        item = ensure_skill_entry(raw_entry, openclaw_home=openclaw_home, dry_run=dry_run)
        result["skills"].append(item)
        result["changed"] = result["changed"] or bool(item.get("changed"))
        result["ok"] = result["ok"] and bool(item.get("ok"))

    for raw_entry in command_entries:
        if not isinstance(raw_entry, dict):
            continue
        item = ensure_command_entry(raw_entry, dry_run=dry_run)
        result["commands"].append(item)
        result["changed"] = result["changed"] or bool(item.get("changed"))
        result["ok"] = result["ok"] and bool(item.get("ok"))

    return result


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    default_openclaw_home = Path(os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw"))).expanduser()
    parser = argparse.ArgumentParser(description="Ensure required runtime skills and command dependencies")
    parser.add_argument("--openclaw-home", default=str(default_openclaw_home))
    parser.add_argument("--manifest", default=str(script_dir / "runtime-required-skills.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    openclaw_home = Path(args.openclaw_home).expanduser()
    manifest_path = Path(args.manifest).expanduser()
    try:
        result = ensure_runtime_skills(
            manifest_path=manifest_path,
            openclaw_home=openclaw_home,
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:
        result = {
            "ok": False,
            "dry_run": bool(args.dry_run),
            "manifest": str(manifest_path),
            "openclaw_home": str(openclaw_home),
            "error": str(exc),
        }

    if args.emit_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"manifest={result.get('manifest', '')}")
        print(f"openclaw_home={result.get('openclaw_home', '')}")
        print(f"ok={str(bool(result.get('ok'))).lower()}")
        print(f"changed={str(bool(result.get('changed'))).lower()}")

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

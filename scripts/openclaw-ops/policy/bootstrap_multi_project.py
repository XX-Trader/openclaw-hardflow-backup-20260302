#!/usr/bin/env python3
"""Bootstrap Policy-Enforcer for multiple projects with adaptive checks."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def run_cmd(
    cmd: list[str],
    cwd: Path | None = None,
    timeout: int = 25,
) -> tuple[int, str, str, bool]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip(), False
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
        return 124, stdout, stderr or "timeout", True
    except Exception as exc:  # pragma: no cover
        return 127, "", str(exc), False


def to_project_id(value: str) -> str:
    key = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return key or "project"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_runtime_files(src_dir: Path, dst_dir: Path) -> list[str]:
    ensure_dir(dst_dir)
    copied: list[str] = []
    for name in [
        "policy_enforcer.py",
        "task_center.py",
        "policy-config.json",
        "routing-rules.json",
        "token-pricing.json",
        "README.md",
    ]:
        src = src_dir / name
        if not src.exists():
            raise FileNotFoundError(f"runtime file missing: {src}")
        dst = dst_dir / name
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        copied.append(str(dst))
    return copied


def check_writable(path: Path) -> tuple[bool, str]:
    probe = path / ".policy_write_test"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def detect_git() -> tuple[bool, str, str]:
    git_path = shutil.which("git") or ""
    if not git_path:
        return False, "", "git not found in PATH"
    rc, out, err, _ = run_cmd([git_path, "--version"], timeout=8)
    if rc != 0:
        return False, git_path, err or "git --version failed"
    return True, git_path, out or "ok"


def load_projects(projects_file: Path | None, project_roots: list[str]) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []

    if projects_file:
        raw = json.loads(projects_file.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = raw.get("projects", [])
        else:
            raise ValueError("projects file must be JSON object or array")

        if not isinstance(items, list):
            raise ValueError("projects must be a list")
        for item in items:
            if not isinstance(item, dict):
                continue
            path_value = str(item.get("path", "")).strip()
            if not path_value:
                continue
            name = str(item.get("name", "")).strip() or Path(path_value).name
            projects.append(
                {
                    "name": name,
                    "path": path_value,
                    "expected_remote": str(item.get("expected_remote", "")).strip(),
                    "remote_name": str(item.get("remote_name", "origin")).strip() or "origin",
                    "check_remote": parse_bool(item.get("check_remote", True), default=True),
                }
            )

    for root in project_roots:
        root = root.strip()
        if not root:
            continue
        projects.append(
            {
                "name": Path(root).name,
                "path": root,
                "expected_remote": "",
                "remote_name": "origin",
                "check_remote": True,
            }
        )

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for proj in projects:
        key = str(Path(proj["path"]).expanduser().resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(proj)

    return deduped


@dataclass(slots=True)
class ProjectCheckResult:
    name: str
    project_id: str
    path: str
    ok: bool
    writable: bool
    git_repo: bool
    git_root: str
    remote_name: str
    git_remote: str
    git_remote_ok: bool
    policy_env: str
    task_db: str
    errors: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "project_id": self.project_id,
            "path": self.path,
            "ok": self.ok,
            "writable": self.writable,
            "git_repo": self.git_repo,
            "git_root": self.git_root,
            "remote_name": self.remote_name,
            "git_remote": self.git_remote,
            "git_remote_ok": self.git_remote_ok,
            "policy_env": self.policy_env,
            "task_db": self.task_db,
            "errors": self.errors,
            "notes": self.notes,
        }


def bootstrap_project(
    project: dict[str, Any],
    shared_policy_dir: Path,
    strict_git_remote: bool,
    git_available: bool,
    git_bin: str,
    remote_timeout: int,
) -> ProjectCheckResult:
    name = str(project.get("name", "")).strip() or "project"
    root = Path(str(project.get("path", "")).strip()).expanduser()
    project_id = to_project_id(name)

    errors: list[str] = []
    notes: list[str] = []

    if not root.exists() or not root.is_dir():
        return ProjectCheckResult(
            name=name,
            project_id=project_id,
            path=str(root),
            ok=False,
            writable=False,
            git_repo=False,
            git_root="",
            git_remote="",
            git_remote_ok=False,
            policy_env="",
            task_db="",
            errors=[f"project path invalid: {root}"],
            notes=[],
        )

    writable, writable_msg = check_writable(root)
    if not writable:
        errors.append(f"project path not writable: {writable_msg}")

    git_repo = False
    git_root = ""
    remote_name = str(project.get("remote_name", "origin")).strip() or "origin"
    git_remote = ""
    git_remote_ok = False

    if not git_available:
        notes.append("git unavailable: skip repository and remote checks")
    else:
        rc, out, err, _ = run_cmd([git_bin, "-C", str(root), "rev-parse", "--show-toplevel"], timeout=10)
        if rc == 0 and out:
            git_repo = True
            git_root = out

            rc, out, err, _ = run_cmd(
                [git_bin, "-C", str(root), "remote", "get-url", remote_name],
                timeout=10,
            )
            if rc == 0 and out:
                git_remote = out
                check_remote = parse_bool(project.get("check_remote", True), default=True)
                if check_remote:
                    rc, _, remote_err, timed_out = run_cmd(
                        [git_bin, "-C", str(root), "ls-remote", "--exit-code", remote_name, "HEAD"],
                        timeout=remote_timeout,
                    )
                    if rc == 0:
                        git_remote_ok = True
                    else:
                        msg = "git remote unreachable or permission denied"
                        if timed_out:
                            msg = "git remote check timeout"
                        detail = remote_err.strip() or msg
                        if strict_git_remote:
                            errors.append(f"{msg}: {detail}")
                        else:
                            notes.append(f"{msg}: {detail}")
                else:
                    notes.append("skip git remote connectivity check")
            else:
                notes.append(f"git remote not configured: {remote_name}")

            expected_remote = str(project.get("expected_remote", "")).strip()
            if expected_remote and git_remote and expected_remote != git_remote:
                errors.append(f"git remote mismatch: expected={expected_remote}, actual={git_remote}")
        else:
            notes.append(f"not a git repository: {err or out or 'unknown'}")

    workflow_dir = root / ".workflow"
    task_dir = workflow_dir / "task-center"
    ensure_dir(task_dir)

    policy_env = workflow_dir / "policy.env"
    task_db = task_dir / "task_center.db"

    policy_env.write_text(
        "\n".join(
            [
                "# Auto-generated by bootstrap_multi_project.py",
                f"# generated_at={now_iso()}",
                "POLICY_ENFORCER_ENABLED=1",
                "POLICY_ENFORCER_STRICT=1",
                f"POLICY_ENFORCER_PY={shlex.quote(str(shared_policy_dir / 'policy_enforcer.py'))}",
                f"POLICY_DB_FILE={shlex.quote(str(task_db))}",
                f"POLICY_FILE={shlex.quote(str(shared_policy_dir / 'policy-config.json'))}",
                f"POLICY_ROUTING_FILE={shlex.quote(str(shared_policy_dir / 'routing-rules.json'))}",
                f"POLICY_PRICING_FILE={shlex.quote(str(shared_policy_dir / 'token-pricing.json'))}",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )

    init_cmd = [
        sys.executable,
        str(shared_policy_dir / "policy_enforcer.py"),
        "--db",
        str(task_db),
        "--policy-file",
        str(shared_policy_dir / "policy-config.json"),
        "--routing-file",
        str(shared_policy_dir / "routing-rules.json"),
        "--pricing-file",
        str(shared_policy_dir / "token-pricing.json"),
        "init",
    ]
    rc, _, err, _ = run_cmd(init_cmd, cwd=root, timeout=25)
    if rc != 0:
        errors.append(f"policy init failed: {err or rc}")

    validate_cmd = [
        sys.executable,
        str(shared_policy_dir / "policy_enforcer.py"),
        "--db",
        str(task_db),
        "--policy-file",
        str(shared_policy_dir / "policy-config.json"),
        "--routing-file",
        str(shared_policy_dir / "routing-rules.json"),
        "--pricing-file",
        str(shared_policy_dir / "token-pricing.json"),
        "validate-runtime",
    ]
    rc, _, err, _ = run_cmd(validate_cmd, cwd=root, timeout=25)
    if rc != 0:
        errors.append(f"policy validate failed: {err or rc}")

    ok = len(errors) == 0

    return ProjectCheckResult(
        name=name,
        project_id=project_id,
        path=str(root),
        ok=ok,
        writable=writable,
        git_repo=git_repo,
        git_root=git_root,
        remote_name=remote_name,
        git_remote=git_remote,
        git_remote_ok=git_remote_ok,
        policy_env=str(policy_env),
        task_db=str(task_db),
        errors=errors,
        notes=notes,
    )


def build_markdown_report(
    generated_at: str,
    shared_policy_dir: Path,
    environment: dict[str, Any],
    results: list[ProjectCheckResult],
) -> str:
    lines: list[str] = []
    lines.append("# Multi-Project Policy Bootstrap Report")
    lines.append("")
    lines.append(f"- generated_at: {generated_at}")
    lines.append(f"- shared_policy_dir: {shared_policy_dir}")
    lines.append(f"- project_count: {len(results)}")
    lines.append("")
    lines.append("## Environment")
    lines.append(f"- python: {environment.get('python', '-')}")
    lines.append(f"- git_found: {environment.get('git_found', False)}")
    lines.append(f"- git_path: {environment.get('git_path', '-')}")
    lines.append(f"- git_info: {environment.get('git_info', '-')}")
    lines.append(f"- openclaw_home: {environment.get('openclaw_home', '-')}")
    lines.append(f"- openclaw_home_writable: {environment.get('openclaw_home_writable', False)}")
    lines.append(f"- shared_policy_dir_writable: {environment.get('shared_policy_dir_writable', False)}")
    lines.append("")

    for item in results:
        lines.append(f"## {item.name}")
        lines.append(f"- ok: {item.ok}")
        lines.append(f"- path: {item.path}")
        lines.append(f"- writable: {item.writable}")
        lines.append(f"- git_repo: {item.git_repo}")
        lines.append(f"- git_root: {item.git_root or '-'}")
        lines.append(f"- remote_name: {item.remote_name}")
        lines.append(f"- git_remote: {item.git_remote or '-'}")
        lines.append(f"- git_remote_ok: {item.git_remote_ok}")
        lines.append(f"- policy_env: {item.policy_env or '-'}")
        lines.append(f"- task_db: {item.task_db or '-'}")
        if item.errors:
            lines.append("- errors:")
            for err in item.errors:
                lines.append(f"  - {err}")
        if item.notes:
            lines.append("- notes:")
            for note in item.notes:
                lines.append(f"  - {note}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap policy-enforcer across multiple projects")
    parser.add_argument("--projects-file", default="", help="JSON file: {projects:[{name,path,...}]}")
    parser.add_argument("--project-root", action="append", default=[], help="project path (repeatable)")
    parser.add_argument(
        "--openclaw-home",
        default=os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")),
        help="OpenClaw home directory",
    )
    parser.add_argument(
        "--shared-policy-dir",
        default="",
        help="shared policy runtime directory (default: $OPENCLAW_HOME/ops/policy)",
    )
    parser.add_argument(
        "--strict-git-remote",
        action="store_true",
        help="fail project if git remote is unreachable",
    )
    parser.add_argument(
        "--remote-timeout",
        type=int,
        default=20,
        help="git remote connectivity check timeout (seconds)",
    )
    parser.add_argument(
        "--report-json",
        default=".workflow/task-center/multi-project-bootstrap-report.json",
        help="output report json path",
    )
    parser.add_argument(
        "--report-md",
        default=".workflow/task-center/multi-project-bootstrap-report.md",
        help="output report markdown path",
    )
    args = parser.parse_args()

    projects_file = Path(args.projects_file).expanduser() if args.projects_file else None
    projects = load_projects(projects_file, args.project_root)
    if not projects:
        print(json.dumps({"ok": False, "error": "no projects provided"}, ensure_ascii=False))
        return 2

    script_policy_dir = Path(__file__).resolve().parent
    openclaw_home = Path(args.openclaw_home).expanduser()
    shared_policy_dir = Path(args.shared_policy_dir).expanduser() if args.shared_policy_dir else openclaw_home / "ops" / "policy"
    ensure_dir(openclaw_home)
    ensure_dir(shared_policy_dir)

    openclaw_home_writable, openclaw_home_msg = check_writable(openclaw_home)
    shared_policy_dir_writable, shared_policy_msg = check_writable(shared_policy_dir)
    git_found, git_path, git_info = detect_git()

    copied_files: list[str] = []
    startup_errors: list[str] = []
    if not openclaw_home_writable:
        startup_errors.append(f"openclaw home not writable: {openclaw_home_msg}")
    if not shared_policy_dir_writable:
        startup_errors.append(f"shared policy dir not writable: {shared_policy_msg}")
    if startup_errors:
        report = {
            "ok": False,
            "generated_at": now_iso(),
            "openclaw_home": str(openclaw_home),
            "shared_policy_dir": str(shared_policy_dir),
            "environment": {
                "python": sys.executable,
                "git_found": git_found,
                "git_path": git_path,
                "git_info": git_info,
                "openclaw_home": str(openclaw_home),
                "openclaw_home_writable": openclaw_home_writable,
                "shared_policy_dir_writable": shared_policy_dir_writable,
            },
            "errors": startup_errors,
            "projects": [],
        }
        print(json.dumps(report, ensure_ascii=False))
        return 2

    copied_files = copy_runtime_files(script_policy_dir, shared_policy_dir)

    generated_at = now_iso()
    environment = {
        "python": sys.executable,
        "git_found": git_found,
        "git_path": git_path,
        "git_info": git_info,
        "openclaw_home": str(openclaw_home),
        "openclaw_home_writable": openclaw_home_writable,
        "shared_policy_dir_writable": shared_policy_dir_writable,
    }
    results: list[ProjectCheckResult] = []
    for project in projects:
        results.append(
            bootstrap_project(
                project=project,
                shared_policy_dir=shared_policy_dir,
                strict_git_remote=args.strict_git_remote,
                git_available=git_found,
                git_bin=git_path,
                remote_timeout=max(5, args.remote_timeout),
            )
        )

    report = {
        "ok": all(item.ok for item in results),
        "generated_at": generated_at,
        "openclaw_home": str(openclaw_home),
        "shared_policy_dir": str(shared_policy_dir),
        "environment": environment,
        "copied_files": copied_files,
        "projects": [item.to_dict() for item in results],
    }

    report_json_path = Path(args.report_json).expanduser()
    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_md_path = Path(args.report_md).expanduser()
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.write_text(
        build_markdown_report(generated_at, shared_policy_dir, environment, results),
        encoding="utf-8",
        newline="\n",
    )

    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

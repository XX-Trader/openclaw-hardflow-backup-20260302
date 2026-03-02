#!/usr/bin/env python3
"""Project index maintainer for multi-project OpenClaw workflows."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from task_center import TaskCenter
except Exception:  # pragma: no cover
    TaskCenter = None

UTC = timezone.utc

DEFAULT_MODULE_GLOBS = [
    "src/**/*.py",
    "src/**/*.ts",
    "src/**/*.tsx",
    "src/**/*.js",
    "src/**/*.jsx",
    "backend/**/*.py",
    "frontend/src/**/*",
    "app/**/*",
    "services/**/*",
]

DEFAULT_API_GLOBS = [
    "**/*api*.py",
    "**/*api*.ts",
    "**/*api*.js",
    "**/openapi*.yml",
    "**/openapi*.yaml",
    "**/openapi*.json",
    "**/routes*.py",
    "**/routes*.ts",
]

DEFAULT_SCRIPT_GLOBS = [
    "scripts/**/*",
    ".workflow/**/*.sh",
    ".workflow/**/*.py",
]

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
}


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as exc:  # pragma: no cover
        return 127, "", str(exc)


def should_ignore(path: Path) -> bool:
    return any(part in DEFAULT_IGNORE_DIRS for part in path.parts)


def list_files_by_globs(root: Path, globs: list[str], max_files: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for pattern in globs:
        for item in root.glob(pattern):
            if not item.is_file():
                continue
            rel = item.relative_to(root).as_posix()
            if rel in seen:
                continue
            if should_ignore(item.relative_to(root)):
                continue
            seen.add(rel)
            out.append(rel)
            if len(out) >= max_files:
                return sorted(out)
    return sorted(out)


def load_registry(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(raw, list):
        projects = raw
    elif isinstance(raw, dict):
        projects = raw.get("projects", [])
    else:
        raise ValueError("registry must be object or list")
    if not isinstance(projects, list):
        raise ValueError("registry.projects must be list")
    result: list[dict[str, Any]] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        root = str(item.get("path", "")).strip()
        if not root:
            continue
        result.append(item)
    return result


@dataclass(slots=True)
class ProjectResult:
    project_id: str
    name: str
    path: str
    ok: bool
    changed: bool
    git_repo: bool
    git_pull_attempted: bool
    git_pull_ok: bool
    errors: list[str]
    outputs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "path": self.path,
            "ok": self.ok,
            "changed": self.changed,
            "git_repo": self.git_repo,
            "git_pull_attempted": self.git_pull_attempted,
            "git_pull_ok": self.git_pull_ok,
            "errors": self.errors,
            "outputs": self.outputs,
        }


def write_if_changed(path: Path, content: str) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def build_index_markdown(
    name: str,
    root: Path,
    git_info: dict[str, Any],
    modules: list[str],
    apis: list[str],
    scripts: list[str],
) -> str:
    lines: list[str] = []
    lines.append(f"# {name} Project Index")
    lines.append("")
    lines.append(f"- generated_at: {now_iso()}")
    lines.append(f"- root: {root}")
    lines.append(f"- git_repo: {git_info.get('git_repo', False)}")
    lines.append(f"- git_branch: {git_info.get('branch', '-')}")
    lines.append(f"- git_remote: {git_info.get('remote', '-')}")
    lines.append(f"- dirty_files: {git_info.get('dirty_count', 0)}")
    lines.append("")
    lines.append("## Workflow")
    lines.append("1. coordinator intake and requirement alignment")
    lines.append("2. project-agent provides project context and index lookup")
    lines.append("3. coordinator planning and risk dispatch")
    lines.append("4. execution agents implement -> tester validates -> feedback loop")
    lines.append("5. policy-enforcer records status/time/token/cost")
    lines.append("")
    lines.append("## Module Files")
    if modules:
        for item in modules:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## API Related Files")
    if apis:
        for item in apis:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Run / Change Scripts")
    if scripts:
        for item in scripts:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Update Rules")
    lines.append("- API/parameters/process changes must update this index in the same commit.")
    lines.append("- project-agent maintains this index; coordinator consumes it for planning.")
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def collect_git_info(root: Path, timeout: int, do_pull: bool, remote: str, branch: str) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    info = {
        "git_repo": False,
        "branch": "",
        "remote": "",
        "dirty_count": 0,
        "pull_attempted": False,
        "pull_ok": False,
    }
    rc, out, err = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=root, timeout=timeout)
    if rc != 0 or out.strip() != "true":
        return info, errors

    info["git_repo"] = True
    rc, out, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, timeout=timeout)
    if rc == 0:
        info["branch"] = out
    rc, out, _ = run_cmd(["git", "remote", "get-url", remote], cwd=root, timeout=timeout)
    if rc == 0:
        info["remote"] = out
    rc, out, _ = run_cmd(["git", "status", "--porcelain"], cwd=root, timeout=timeout)
    if rc == 0 and out:
        info["dirty_count"] = len([x for x in out.splitlines() if x.strip()])

    if do_pull:
        info["pull_attempted"] = True
        target_branch = branch or str(info["branch"] or "HEAD")
        rc, _, err = run_cmd(["git", "pull", "--ff-only", remote, target_branch], cwd=root, timeout=timeout)
        info["pull_ok"] = rc == 0
        if rc != 0:
            errors.append(f"git pull failed: {err or rc}")
    return info, errors


def normalize_project_id(value: str) -> str:
    base = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.lower()).strip("-")
    return base or "project"


def maintain_project(item: dict[str, Any], git_pull_flag: bool, timeout: int, max_files: int) -> ProjectResult:
    name = str(item.get("name", "")).strip() or Path(str(item["path"])).name
    project_id = normalize_project_id(str(item.get("id", "")).strip() or name)
    root = Path(str(item["path"])).expanduser()
    errors: list[str] = []
    outputs: list[str] = []
    changed = False

    if not root.exists() or not root.is_dir():
        return ProjectResult(project_id, name, str(root), False, False, False, False, False, ["project path invalid"], [])

    index_dir = str(item.get("index_dir", ".workflow/project-index")).strip() or ".workflow/project-index"
    index_root = root / index_dir

    git_pull = bool(item.get("auto_pull", True)) and git_pull_flag
    remote = str(item.get("git_remote", "origin")).strip() or "origin"
    branch = str(item.get("git_branch", "")).strip()
    git_info, git_errors = collect_git_info(root, timeout=timeout, do_pull=git_pull, remote=remote, branch=branch)
    errors.extend(git_errors)

    module_globs = item.get("module_globs") or DEFAULT_MODULE_GLOBS
    api_globs = item.get("api_globs") or DEFAULT_API_GLOBS
    script_globs = item.get("script_globs") or DEFAULT_SCRIPT_GLOBS
    if not isinstance(module_globs, list):
        module_globs = DEFAULT_MODULE_GLOBS
    if not isinstance(api_globs, list):
        api_globs = DEFAULT_API_GLOBS
    if not isinstance(script_globs, list):
        script_globs = DEFAULT_SCRIPT_GLOBS

    modules = list_files_by_globs(root, [str(x) for x in module_globs], max_files=max_files)
    apis = list_files_by_globs(root, [str(x) for x in api_globs], max_files=max_files)
    scripts = list_files_by_globs(root, [str(x) for x in script_globs], max_files=max_files)

    index_md = build_index_markdown(name, root, git_info, modules, apis, scripts)
    changed = write_if_changed(index_root / "PROJECT_INDEX.md", index_md) or changed
    outputs.append(str(index_root / "PROJECT_INDEX.md"))

    index_json = {
        "project_id": project_id,
        "name": name,
        "path": str(root),
        "generated_at": now_iso(),
        "git": git_info,
        "modules": modules,
        "apis": apis,
        "scripts": scripts,
    }
    changed = write_if_changed(index_root / "project-index.json", json.dumps(index_json, ensure_ascii=False, indent=2) + "\n") or changed
    outputs.append(str(index_root / "project-index.json"))

    ok = len(errors) == 0
    return ProjectResult(
        project_id=project_id,
        name=name,
        path=str(root),
        ok=ok,
        changed=changed,
        git_repo=bool(git_info["git_repo"]),
        git_pull_attempted=bool(git_info["pull_attempted"]),
        git_pull_ok=bool(git_info["pull_ok"]),
        errors=errors,
        outputs=outputs,
    )


def write_task_event(task_db: str, task_id: str, actor: str, report: dict[str, Any]) -> None:
    if not TaskCenter:
        return
    db = TaskCenter(task_db)
    try:
        db.init_schema()
        db.add_event(
            task_id=task_id,
            actor=actor,
            event_type="project_index_maintained",
            stage="project-index",
            details={"report_summary": {"ok": report["ok"], "project_count": report["project_count"]}},
        )
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain project index docs for multi-project workflows")
    parser.add_argument("--registry", required=True, help="registry json path")
    parser.add_argument("--git-pull", action="store_true", help="perform git pull on each project if git repo")
    parser.add_argument("--timeout", type=int, default=30, help="command timeout seconds")
    parser.add_argument("--max-files", type=int, default=300, help="max listed files per category")
    parser.add_argument("--output", default="", help="write report json path")
    parser.add_argument("--emit-json", action="store_true", help="print full report json to stdout")
    parser.add_argument("--task-db", default="", help="optional task center sqlite path")
    parser.add_argument("--task-id", default="", help="optional task id for event logging")
    parser.add_argument("--actor", default="project-agent", help="event actor")
    args = parser.parse_args()

    registry = Path(args.registry).expanduser()
    projects = load_registry(registry)
    results: list[ProjectResult] = []
    for item in projects:
        results.append(
            maintain_project(
                item=item,
                git_pull_flag=bool(args.git_pull),
                timeout=max(5, int(args.timeout)),
                max_files=max(50, int(args.max_files)),
            )
        )

    report = {
        "ok": all(x.ok for x in results),
        "generated_at": now_iso(),
        "registry": str(registry),
        "project_count": len(results),
        "changed_count": len([x for x in results if x.changed]),
        "projects": [x.to_dict() for x in results],
    }

    if args.output:
        out = Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.task_db and args.task_id:
        write_task_event(task_db=args.task_db, task_id=args.task_id, actor=args.actor, report=report)

    if args.emit_json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        if report["changed_count"] == 0 and report["ok"]:
            print("NO_REPLY")
        else:
            print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

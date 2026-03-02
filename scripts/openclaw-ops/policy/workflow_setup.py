#!/usr/bin/env python3
"""Interactive setup/init wizard for OpenClaw hardflow policy runtime."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc
API_ENGINES = {"http", "playwright", "selenium"}


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 20) -> tuple[int, str, str, bool]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip(), False
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or "").strip() if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else ""
        return 124, stdout, stderr or "timeout", True
    except Exception as exc:  # pragma: no cover
        return 127, "", str(exc), False


def is_writable_dir(path: Path) -> tuple[bool, str]:
    if not path.exists() or not path.is_dir():
        return False, f"path not found: {path}"
    probe = path / ".openclaw_setup_probe"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def slugify(text: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9_-]+", "-", text.strip().lower()).strip("-")
    return out or "project"


def parse_bool_input(text: str, default: bool) -> bool:
    val = text.strip().lower()
    if val == "":
        return default
    if val in {"1", "y", "yes", "true", "t"}:
        return True
    if val in {"0", "n", "no", "false", "f"}:
        return False
    return default


def normalize_log_mode(text: str, default: str = "silent") -> str:
    mode = text.strip().lower()
    if mode in {"silent", "chat"}:
        return mode
    return default


def normalize_api_engine(text: str, default: str = "playwright") -> str:
    engine = text.strip().lower()
    if engine in API_ENGINES:
        return engine
    return default


def prompt_text(message: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = input(f"{message}{suffix}: ").strip()
    return raw if raw else default


def prompt_yes_no(message: str, default: bool = True) -> bool:
    default_text = "Y/n" if default else "y/N"
    raw = input(f"{message} [{default_text}]: ").strip()
    return parse_bool_input(raw, default=default)


def split_csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def load_projects_file(path: Path) -> list[Path]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    items = data if isinstance(data, list) else data.get("projects", [])
    out: list[Path] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("path", "")).strip()
        if raw:
            out.append(Path(raw).expanduser())
    return out


def discover_repo_candidates(scan_roots: list[Path], max_depth: int, max_projects: int) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()

    for root in scan_roots:
        if not root.exists() or not root.is_dir():
            continue
        root_abs = root.resolve()
        for cur, dirs, _files in os.walk(root_abs):
            cur_path = Path(cur)
            rel_depth = len(cur_path.relative_to(root_abs).parts)
            if rel_depth > max_depth:
                dirs[:] = []
                continue

            git_dir = cur_path / ".git"
            is_repo = git_dir.is_dir() or git_dir.is_file()
            if is_repo:
                key = str(cur_path.resolve())
                if key not in seen:
                    seen.add(key)
                    found.append(cur_path)
                    if len(found) >= max_projects:
                        return sorted(found)
                dirs[:] = []
                continue

            # prune heavy directories
            dirs[:] = [d for d in dirs if d not in {"node_modules", ".venv", "venv", "__pycache__", ".git"}]

    return sorted(found)


def detect_project_signals(path: Path) -> list[str]:
    signals: list[str] = []
    checks = {
        "docker-compose": [
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
        ],
        "dockerfile": ["Dockerfile"],
        "kubernetes": ["k8s", "helm/Chart.yaml"],
        "python": ["pyproject.toml", "requirements.txt", "manage.py"],
        "node": ["package.json"],
        "go": ["go.mod"],
        "java": ["pom.xml", "build.gradle"],
    }
    for key, markers in checks.items():
        for marker in markers:
            if (path / marker).exists():
                signals.append(key)
                break
    deploy_scripts = list(path.glob("scripts/deploy*.sh")) + list(path.glob("scripts/*deploy*.py"))
    if deploy_scripts:
        signals.append("deploy-script")
    if (path / "scripts" / "hardflow" / "hardflow-run.sh").exists():
        signals.append("hardflow")
    return sorted(set(signals))


def infer_deploy_plan(path: Path, signals: list[str]) -> dict[str, Any]:
    reason = ""
    strategy = "manual"
    commands: list[str] = []

    if "kubernetes" in signals:
        strategy = "kubernetes"
        reason = "detected k8s/helm assets"
        commands = [
            "kubectl apply -f k8s/",
            "kubectl rollout status deployment/<name> -n <namespace>",
        ]
    elif "docker-compose" in signals:
        strategy = "docker-compose"
        reason = "detected compose manifest"
        commands = [
            "docker compose pull",
            "docker compose up -d --build",
            "docker compose ps",
        ]
    elif "deploy-script" in signals:
        strategy = "script-first"
        reason = "detected deploy script under scripts/"
        commands = [
            "bash scripts/deploy-prod.sh  # or your deploy script",
            "verify service health endpoint",
        ]
    elif "python" in signals and "node" in signals:
        strategy = "fullstack-systemd"
        reason = "detected python + node"
        commands = [
            "python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt",
            "npm ci && npm run build",
            "configure systemd/nginx for backend+frontend",
        ]
    elif "python" in signals:
        strategy = "python-systemd"
        reason = "detected python service markers"
        commands = [
            "python -m venv .venv && . .venv/bin/activate",
            "pip install -r requirements.txt  # or pip install .",
            "systemctl restart <service>",
        ]
    elif "node" in signals:
        strategy = "node-pm2-or-systemd"
        reason = "detected package.json"
        commands = [
            "npm ci",
            "npm run build",
            "pm2 restart <app>  # or systemd restart",
        ]
    elif "go" in signals:
        strategy = "go-systemd"
        reason = "detected go.mod"
        commands = [
            "go build -o bin/app ./...",
            "systemctl restart <service>",
        ]
    elif "java" in signals:
        strategy = "java-systemd"
        reason = "detected maven/gradle markers"
        commands = [
            "mvn -DskipTests package  # or ./gradlew build",
            "systemctl restart <service>",
        ]
    else:
        reason = "no standard deployment marker detected"
        commands = [
            "add project-specific deploy command",
            "verify health and rollback strategy",
        ]

    if "hardflow" in signals:
        commands.append("bash scripts/hardflow/hardflow-run.sh deploy")

    return {
        "strategy": strategy,
        "reason": reason,
        "commands": commands,
        "detected_signals": signals,
        "project_path": str(path),
    }


@dataclass(slots=True)
class ProjectAssessment:
    name: str
    path: Path
    writable: bool
    writable_note: str
    git_repo: bool
    branch: str
    remote_name: str
    remote_url: str
    remote_read_ok: bool | None
    remote_read_note: str
    remote_push_ok: bool | None
    remote_push_note: str
    deploy_plan: dict[str, Any]
    hints: list[str]

    def to_registry_item(self) -> dict[str, Any]:
        return {
            "id": slugify(self.name),
            "name": self.name,
            "path": str(self.path),
            "index_dir": ".workflow/project-index",
            "auto_pull": True,
            "git_remote": self.remote_name or "origin",
            "git_branch": self.branch or "main",
            "deployment": self.deploy_plan,
            "setup_hints": self.hints,
        }

    def to_bootstrap_item(self, strict_remote: bool) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "remote_name": self.remote_name or "origin",
            "expected_remote": self.remote_url if strict_remote and self.remote_url else "",
            "check_remote": bool(strict_remote),
        }


def assess_project(path: Path, git_bin: str, strict_remote: bool) -> ProjectAssessment:
    abs_path = path.expanduser().resolve()
    writable, writable_note = is_writable_dir(abs_path)
    name = abs_path.name
    remote_name = "origin"

    git_repo = False
    branch = ""
    remote_url = ""
    remote_read_ok: bool | None = None
    remote_read_note = "not checked"
    remote_push_ok: bool | None = None
    remote_push_note = "not checked"
    hints: list[str] = []

    rc, out, err, _ = run_cmd([git_bin, "-C", str(abs_path), "rev-parse", "--is-inside-work-tree"], timeout=10)
    if rc == 0 and out.strip().lower() == "true":
        git_repo = True
        rc, out, _err, _ = run_cmd([git_bin, "-C", str(abs_path), "rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
        if rc == 0:
            branch = out.strip()

        rc, out, err, _ = run_cmd([git_bin, "-C", str(abs_path), "remote", "get-url", remote_name], timeout=10)
        if rc == 0 and out:
            remote_url = out.strip()
            rc, _out, err, timed_out = run_cmd(
                [git_bin, "-C", str(abs_path), "ls-remote", "--exit-code", remote_name, "HEAD"],
                timeout=15,
            )
            if rc == 0:
                remote_read_ok = True
                remote_read_note = "ok"
            else:
                remote_read_ok = False
                remote_read_note = err or ("timeout" if timed_out else f"exit={rc}")
                hints.append("Git remote read failed: check SSH key/token/network.")

            rc, _out, err, timed_out = run_cmd(
                [git_bin, "-C", str(abs_path), "push", "--dry-run", remote_name, "HEAD"],
                timeout=15,
            )
            if rc == 0:
                remote_push_ok = True
                remote_push_note = "ok"
            else:
                remote_push_ok = False
                remote_push_note = err or ("timeout" if timed_out else f"exit={rc}")
                hints.append("Git push dry-run failed: verify write permission/deploy key.")
        else:
            remote_read_ok = False
            remote_read_note = err or "remote not configured"
            remote_push_ok = False
            remote_push_note = "remote not configured"
            hints.append("Git remote missing: run `git remote add origin <repo-url>`.")
    else:
        hints.append("Not a git repository: initialize git or provide correct project path.")

    if not writable:
        hints.append("Path not writable: fix filesystem permission before bootstrap.")
    if strict_remote and remote_read_ok is False:
        hints.append("Strict remote check is enabled; this project may fail bootstrap.")

    signals = detect_project_signals(abs_path)
    deploy_plan = infer_deploy_plan(abs_path, signals)
    return ProjectAssessment(
        name=name,
        path=abs_path,
        writable=writable,
        writable_note=writable_note,
        git_repo=git_repo,
        branch=branch,
        remote_name=remote_name,
        remote_url=remote_url,
        remote_read_ok=remote_read_ok,
        remote_read_note=remote_read_note,
        remote_push_ok=remote_push_ok,
        remote_push_note=remote_push_note,
        deploy_plan=deploy_plan,
        hints=hints,
    )


def merge_registry(existing: dict[str, Any], incoming: list[dict[str, Any]]) -> dict[str, Any]:
    cur = existing.get("projects", [])
    if not isinstance(cur, list):
        cur = []
    by_path: dict[str, dict[str, Any]] = {}
    for item in cur:
        if isinstance(item, dict):
            key = str(item.get("path", "")).strip()
            if key:
                by_path[key] = item
    for item in incoming:
        key = str(item.get("path", "")).strip()
        if key:
            by_path[key] = item
    return {"projects": sorted(by_path.values(), key=lambda x: str(x.get("name", "")).lower())}


def read_json_object(path: Path, default_obj: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default_obj
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else default_obj


def write_markdown_report(
    path: Path,
    mode: str,
    openclaw_home: Path,
    strict_remote: bool,
    dry_run: bool,
    selected: list[ProjectAssessment],
    bootstrap_result: dict[str, Any] | None,
    install_job_result: dict[str, Any] | None,
    cron_setup_result: dict[str, Any] | None,
) -> None:
    lines: list[str] = []
    lines.append(f"# OpenClaw Workflow {mode.title()} Report")
    lines.append("")
    lines.append(f"- generated_at: {now_iso()}")
    lines.append(f"- openclaw_home: {openclaw_home}")
    lines.append(f"- strict_git_remote: {strict_remote}")
    lines.append(f"- dry_run: {dry_run}")
    lines.append(f"- project_count: {len(selected)}")
    lines.append("")

    for item in selected:
        lines.append(f"## {item.name}")
        lines.append(f"- path: {item.path}")
        lines.append(f"- writable: {item.writable} ({item.writable_note})")
        lines.append(f"- git_repo: {item.git_repo}")
        lines.append(f"- branch: {item.branch or '-'}")
        lines.append(f"- remote: {item.remote_url or '-'}")
        lines.append(f"- remote_read_ok: {item.remote_read_ok}")
        lines.append(f"- remote_push_ok: {item.remote_push_ok}")
        lines.append(f"- deploy_strategy: {item.deploy_plan.get('strategy')}")
        lines.append(f"- deploy_reason: {item.deploy_plan.get('reason')}")
        lines.append("- deploy_commands:")
        for cmd in item.deploy_plan.get("commands", []):
            lines.append(f"  - {cmd}")
        if item.hints:
            lines.append("- hints:")
            for hint in item.hints:
                lines.append(f"  - {hint}")
        lines.append("")

    lines.append("## Apply Result")
    if bootstrap_result is not None:
        lines.append(f"- bootstrap_ok: {bootstrap_result.get('ok')}")
        lines.append(f"- bootstrap_report_json: {bootstrap_result.get('report_json', '-')}")
        lines.append(f"- bootstrap_report_md: {bootstrap_result.get('report_md', '-')}")
    else:
        lines.append("- bootstrap: skipped")
    if install_job_result is not None:
        lines.append(f"- install_job_ok: {install_job_result.get('ok')}")
        lines.append(f"- install_job_note: {install_job_result.get('note', '-')}")
    else:
        lines.append("- install_job: skipped")
    if cron_setup_result is not None:
        lines.append(f"- cron_setup_ok: {cron_setup_result.get('ok')}")
        lines.append(f"- cron_setup_note: {cron_setup_result.get('note', '-')}")
    else:
        lines.append("- cron_setup: skipped")
    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def parse_index_selection(raw: str, max_index: int) -> list[int]:
    text = raw.strip().lower()
    if text in {"all", "*"}:
        return list(range(1, max_index + 1))
    if text in {"none", ""}:
        return []
    picked: set[int] = set()
    for token in split_csv(text):
        if "-" in token:
            left, right = token.split("-", 1)
            if left.isdigit() and right.isdigit():
                lo, hi = int(left), int(right)
                for idx in range(min(lo, hi), max(lo, hi) + 1):
                    if 1 <= idx <= max_index:
                        picked.add(idx)
            continue
        if token.isdigit():
            idx = int(token)
            if 1 <= idx <= max_index:
                picked.add(idx)
    return sorted(picked)


def choose_projects_interactive(candidates: list[Path]) -> list[Path]:
    if not candidates:
        return []
    print("Discovered project candidates:")
    for idx, path in enumerate(candidates, start=1):
        print(f"  {idx:>2}. {path}")
    raw = prompt_text("Select project indexes (e.g. 1,2,4-6 | all | none)", "all")
    selected_idx = parse_index_selection(raw, len(candidates))
    return [candidates[i - 1] for i in selected_idx]


def run_bootstrap(
    script_path: Path,
    projects_file: Path,
    openclaw_home: Path,
    strict_remote: bool,
    report_json: Path,
    report_md: Path,
) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        str(script_path),
        "--projects-file",
        str(projects_file),
        "--openclaw-home",
        str(openclaw_home),
        "--report-json",
        str(report_json),
        "--report-md",
        str(report_md),
    ]
    if strict_remote:
        cmd.append("--strict-git-remote")
    rc, out, err, _ = run_cmd(cmd, timeout=180)
    if rc == 0:
        return True, out or "ok"
    return False, err or out or f"bootstrap exit={rc}"


def run_install_job(
    script_path: Path,
    openclaw_home: Path,
    registry_file: Path,
    channel: str,
    target: str,
) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        str(script_path),
        "--jobs-file",
        str(openclaw_home / "cron" / "jobs.json"),
        "--maintainer-py",
        str(openclaw_home / "ops" / "policy" / "project_index_maintainer.py"),
        "--registry",
        str(registry_file),
    ]
    if channel:
        cmd.extend(["--channel", channel])
    if target:
        cmd.extend(["--to", target])
    rc, out, err, _ = run_cmd(cmd, timeout=60)
    if rc == 0:
        return True, out or "ok"
    return False, err or out or f"install job exit={rc}"


def run_cron_setup(
    script_path: Path,
    openclaw_home: Path,
    channel: str,
    target: str,
    incremental_every_ms: int,
    full_expr: str,
    daily_expr: str,
    daily_major_only: bool,
    incremental_log_mode: str,
    full_log_mode: str,
    daily_log_mode: str,
    install_system_schedule_job: bool,
    system_log_mode: str,
    install_api_test_job: bool,
    api_test_expr: str,
    api_test_engine: str,
    api_test_log_mode: str,
    install_daily_work_job: bool,
    daily_work_expr: str,
    daily_work_log_mode: str,
    dingtalk_webhook_env: str,
    dingtalk_secret_env: str,
    install_self_evolution_job: bool,
    self_evolution_expr: str,
    self_evolution_log_mode: str,
    self_evolution_min_interval_days: int,
    self_evolution_max_tasks_per_run: int,
) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        str(script_path),
        "--jobs-file",
        str(openclaw_home / "cron" / "jobs.json"),
        "--runner-py",
        str(openclaw_home / "ops" / "ops_cron_runner.py"),
        "--config-file",
        str(openclaw_home / "ops" / "cron-monitor-config.json"),
        "--state-file",
        str(openclaw_home / "ops" / "cron-monitor-state.json"),
        "--history-dir",
        str(openclaw_home / "ops" / "cron-runs"),
        "--incremental-every-ms",
        str(int(incremental_every_ms)),
        "--full-expr",
        full_expr,
        "--daily-expr",
        daily_expr,
        "--incremental-log-mode",
        incremental_log_mode,
        "--full-log-mode",
        full_log_mode,
        "--daily-log-mode",
        daily_log_mode,
    ]
    if daily_major_only:
        cmd.append("--daily-major-only")
    if install_system_schedule_job:
        cmd.append("--install-system-schedule-job")
        cmd.extend(["--system-log-mode", system_log_mode])
    if install_api_test_job:
        cmd.append("--install-api-test-job")
        cmd.extend(
            [
                "--api-test-expr",
                api_test_expr,
                "--api-test-engine",
                normalize_api_engine(api_test_engine),
                "--api-test-log-mode",
                api_test_log_mode,
            ]
        )
    if install_daily_work_job:
        cmd.append("--install-daily-work-job")
        cmd.extend(
            [
                "--daily-work-expr",
                daily_work_expr,
                "--daily-work-log-mode",
                daily_work_log_mode,
                "--dingtalk-webhook-env",
                dingtalk_webhook_env,
                "--dingtalk-secret-env",
                dingtalk_secret_env,
            ]
        )
    if install_self_evolution_job:
        cmd.append("--install-self-evolution-job")
        cmd.extend(
            [
                "--self-evolution-expr",
                self_evolution_expr,
                "--self-evolution-log-mode",
                self_evolution_log_mode,
                "--self-evolution-min-interval-days",
                str(max(1, int(self_evolution_min_interval_days))),
                "--self-evolution-max-tasks-per-run",
                str(max(1, int(self_evolution_max_tasks_per_run))),
            ]
        )
    if channel:
        cmd.extend(["--channel", channel])
    if target:
        cmd.extend(["--to", target])
    rc, out, err, _ = run_cmd(cmd, timeout=90)
    if rc == 0:
        return True, out or "ok"
    return False, err or out or f"cron setup exit={rc}"


def main() -> int:
    home = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
    parser = argparse.ArgumentParser(description="OpenClaw workflow setup/init wizard")
    parser.add_argument("mode", nargs="?", default="init", choices=["init", "setup"], help="wizard mode")
    parser.add_argument("--openclaw-home", default=str(Path(os.environ.get("OPENCLAW_HOME", home / ".openclaw"))))
    parser.add_argument("--scan-root", action="append", default=[])
    parser.add_argument("--include-path", action="append", default=[])
    parser.add_argument("--projects-file", default="")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--max-projects", type=int, default=200)
    parser.add_argument("--strict-git-remote", action="store_true")
    parser.add_argument("--install-index-job", action="store_true")
    parser.add_argument("--install-cron-setup", action="store_true")
    parser.add_argument("--job-channel", default="")
    parser.add_argument("--job-to", default="")
    parser.add_argument("--cron-channel", default="")
    parser.add_argument("--cron-to", default="")
    parser.add_argument("--cron-incremental-every-ms", type=int, default=900000)
    parser.add_argument("--cron-full-expr", default="23 */6 * * *")
    parser.add_argument("--cron-daily-expr", default="5 0 * * *")
    parser.add_argument("--cron-daily-major-only", action="store_true")
    parser.add_argument("--cron-incremental-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--cron-full-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--cron-daily-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--cron-install-system-schedule-job", action="store_true")
    parser.add_argument("--cron-system-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--cron-install-api-test-job", action="store_true")
    parser.add_argument("--cron-api-test-expr", default="*/15 * * * *")
    parser.add_argument("--cron-api-test-engine", default="playwright", choices=sorted(API_ENGINES))
    parser.add_argument("--cron-api-test-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--cron-install-daily-work-job", action="store_true")
    parser.add_argument("--cron-daily-work-expr", default="15 0 * * *")
    parser.add_argument("--cron-daily-work-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--cron-dingtalk-webhook-env", default="DINGTALK_WEBHOOK_URL")
    parser.add_argument("--cron-dingtalk-secret-env", default="DINGTALK_SECRET")
    parser.add_argument("--cron-install-self-evolution-job", action="store_true")
    parser.add_argument("--cron-self-evolution-expr", default="30 3 * * 1")
    parser.add_argument("--cron-self-evolution-log-mode", default="silent", choices=["silent", "chat"])
    parser.add_argument("--cron-self-evolution-min-interval-days", type=int, default=7)
    parser.add_argument("--cron-self-evolution-max-tasks-per-run", type=int, default=3)
    parser.add_argument("--yes", action="store_true", help="non-interactive with defaults")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    interactive = (not args.yes) and sys.stdin.isatty() and sys.stdout.isatty()
    openclaw_home = Path(args.openclaw_home).expanduser()
    policy_dir = Path(__file__).resolve().parent
    bootstrap_py = policy_dir / "bootstrap_multi_project.py"
    install_job_py = policy_dir.parent / "install_project_index_job.py"
    cron_setup_py = policy_dir.parent / "cron_setup.py"
    task_center_dir = openclaw_home / "ops" / "task-center"
    setup_dir = task_center_dir / "workflow-setup"
    ensure_dir(setup_dir)
    ensure_dir(task_center_dir)

    git_bin = shutil.which("git") or ""
    if not git_bin:
        print(json.dumps({"ok": False, "error": "git not found in PATH"}, ensure_ascii=False))
        return 2

    scan_roots: list[Path] = [Path(x).expanduser() for x in args.scan_root if str(x).strip()]
    if interactive and not scan_roots:
        raw_roots = prompt_text("Scan roots (comma separated)", str(Path.cwd()))
        scan_roots = [Path(x).expanduser() for x in split_csv(raw_roots)]
    if not scan_roots:
        scan_roots = [Path.cwd()]

    include_paths: list[Path] = [Path(x).expanduser() for x in args.include_path if str(x).strip()]
    if args.projects_file:
        include_paths.extend(load_projects_file(Path(args.projects_file).expanduser()))

    strict_remote = bool(args.strict_git_remote)
    install_index_job = bool(args.install_index_job)
    install_cron_setup = bool(args.install_cron_setup)
    install_system_schedule_job = bool(args.cron_install_system_schedule_job)
    install_api_test_job = bool(args.cron_install_api_test_job)
    install_daily_work_job = bool(args.cron_install_daily_work_job)
    install_self_evolution_job = bool(args.cron_install_self_evolution_job)
    dry_run = bool(args.dry_run)

    if interactive:
        strict_remote = prompt_yes_no("Enable strict git remote check during bootstrap", default=strict_remote)
        if not include_paths:
            extra = prompt_text("Extra project paths (comma separated, optional)", "")
            if extra:
                include_paths.extend([Path(x).expanduser() for x in split_csv(extra)])

    candidates = discover_repo_candidates(
        scan_roots=scan_roots,
        max_depth=max(1, int(args.max_depth)),
        max_projects=max(1, int(args.max_projects)),
    )

    selected_paths: list[Path]
    if interactive:
        selected_paths = choose_projects_interactive(candidates)
    else:
        selected_paths = list(candidates)

    for path in include_paths:
        p = path.resolve() if path.exists() else path
        if p not in selected_paths:
            selected_paths.append(p)

    # de-duplicate by resolved path string
    dedup: dict[str, Path] = {}
    for item in selected_paths:
        key = str(item.expanduser().resolve()) if item.exists() else str(item.expanduser())
        dedup[key] = item
    selected_paths = sorted(dedup.values(), key=lambda x: str(x))

    if not selected_paths:
        payload = {
            "ok": False,
            "error": "no project selected",
            "scan_roots": [str(x) for x in scan_roots],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 2

    assessments: list[ProjectAssessment] = [
        assess_project(path=path, git_bin=git_bin, strict_remote=strict_remote) for path in selected_paths
    ]

    if interactive:
        print("")
        print("Project assessment summary:")
        for idx, item in enumerate(assessments, start=1):
            print(
                f"  {idx:>2}. {item.name} | writable={item.writable} | git={item.git_repo} "
                f"| remote_read={item.remote_read_ok} | deploy={item.deploy_plan.get('strategy')}"
            )
        dry_run = not prompt_yes_no("Apply setup now", default=not dry_run)
        if not dry_run:
            install_index_job = prompt_yes_no("Install project-index cron job", default=install_index_job)
            if install_index_job:
                args.job_channel = prompt_text("Job delivery channel (optional)", args.job_channel or "")
                args.job_to = prompt_text("Job delivery target (optional)", args.job_to or "")
            install_cron_setup = prompt_yes_no("Install hardflow cron setup jobs", default=install_cron_setup)
            if install_cron_setup:
                args.cron_channel = prompt_text("Cron delivery channel (optional)", args.cron_channel or "")
                args.cron_to = prompt_text("Cron delivery target (optional)", args.cron_to or "")
                install_system_schedule_job = prompt_yes_no(
                    "Install system schedule audit skill/job", default=install_system_schedule_job or True
                )
                install_api_test_job = prompt_yes_no(
                    "Install API full test audit job (single-pass)", default=install_api_test_job or True
                )
                install_daily_work_job = prompt_yes_no(
                    "Install daily work DingTalk report job", default=install_daily_work_job or True
                )
                install_self_evolution_job = prompt_yes_no(
                    "Install weekly self-evolution TODO packager job", default=install_self_evolution_job or True
                )
                args.cron_incremental_log_mode = normalize_log_mode(
                    prompt_text("Incremental log mode (silent/chat)", args.cron_incremental_log_mode or "silent"),
                    default="silent",
                )
                args.cron_full_log_mode = normalize_log_mode(
                    prompt_text("Full log mode (silent/chat)", args.cron_full_log_mode or "silent"),
                    default="silent",
                )
                args.cron_daily_log_mode = normalize_log_mode(
                    prompt_text("Daily log mode (silent/chat)", args.cron_daily_log_mode or "silent"),
                    default="silent",
                )
                args.cron_system_log_mode = normalize_log_mode(
                    prompt_text("System schedule log mode (silent/chat)", args.cron_system_log_mode or "silent"),
                    default="silent",
                )
                if install_api_test_job:
                    args.cron_api_test_expr = prompt_text(
                        "API test cron expr", args.cron_api_test_expr or "*/15 * * * *"
                    )
                    args.cron_api_test_engine = normalize_api_engine(
                        prompt_text("API test engine (http/playwright/selenium)", args.cron_api_test_engine or "playwright"),
                        default="playwright",
                    )
                    args.cron_api_test_log_mode = normalize_log_mode(
                        prompt_text("API test log mode (silent/chat)", args.cron_api_test_log_mode or "silent"),
                        default="silent",
                    )
                if install_daily_work_job:
                    args.cron_daily_work_expr = prompt_text(
                        "Daily work report cron expr", args.cron_daily_work_expr or "15 0 * * *"
                    )
                    args.cron_daily_work_log_mode = normalize_log_mode(
                        prompt_text(
                            "Daily work report log mode (silent/chat)",
                            args.cron_daily_work_log_mode or "silent",
                        ),
                        default="silent",
                    )
                    args.cron_dingtalk_webhook_env = prompt_text(
                        "DingTalk webhook env", args.cron_dingtalk_webhook_env or "DINGTALK_WEBHOOK_URL"
                    )
                    args.cron_dingtalk_secret_env = prompt_text(
                        "DingTalk secret env", args.cron_dingtalk_secret_env or "DINGTALK_SECRET"
                    )
                if install_self_evolution_job:
                    args.cron_self_evolution_expr = prompt_text(
                        "Self-evolution weekly cron expr", args.cron_self_evolution_expr or "30 3 * * 1"
                    )
                    args.cron_self_evolution_log_mode = normalize_log_mode(
                        prompt_text(
                            "Self-evolution log mode (silent/chat)",
                            args.cron_self_evolution_log_mode or "silent",
                        ),
                        default="silent",
                    )
                    args.cron_self_evolution_min_interval_days = int(
                        prompt_text(
                            "Self-evolution min interval days",
                            str(args.cron_self_evolution_min_interval_days or 7),
                        )
                        or "7"
                    )
                    args.cron_self_evolution_max_tasks_per_run = int(
                        prompt_text(
                            "Self-evolution max tasks per run",
                            str(args.cron_self_evolution_max_tasks_per_run or 3),
                        )
                        or "3"
                    )

    args.cron_incremental_log_mode = normalize_log_mode(args.cron_incremental_log_mode or "silent", default="silent")
    args.cron_full_log_mode = normalize_log_mode(args.cron_full_log_mode or "silent", default="silent")
    args.cron_daily_log_mode = normalize_log_mode(args.cron_daily_log_mode or "silent", default="silent")
    args.cron_system_log_mode = normalize_log_mode(args.cron_system_log_mode or "silent", default="silent")
    args.cron_api_test_log_mode = normalize_log_mode(args.cron_api_test_log_mode or "silent", default="silent")
    args.cron_daily_work_log_mode = normalize_log_mode(args.cron_daily_work_log_mode or "silent", default="silent")
    args.cron_self_evolution_log_mode = normalize_log_mode(
        args.cron_self_evolution_log_mode or "silent", default="silent"
    )
    args.cron_api_test_engine = normalize_api_engine(args.cron_api_test_engine or "playwright", default="playwright")
    args.cron_self_evolution_min_interval_days = max(1, int(args.cron_self_evolution_min_interval_days or 7))
    args.cron_self_evolution_max_tasks_per_run = max(1, int(args.cron_self_evolution_max_tasks_per_run or 3))

    generated_projects_file = setup_dir / "projects.generated.json"
    projects_payload = {"projects": [x.to_bootstrap_item(strict_remote=strict_remote) for x in assessments]}
    generated_projects_file.write_text(json.dumps(projects_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    registry_file = task_center_dir / "project-registry.json"
    existing_registry = read_json_object(registry_file, {"projects": []})
    merged_registry = merge_registry(existing_registry, [x.to_registry_item() for x in assessments])
    registry_file.write_text(json.dumps(merged_registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    bootstrap_report_json = setup_dir / "bootstrap-report.json"
    bootstrap_report_md = setup_dir / "bootstrap-report.md"
    bootstrap_result: dict[str, Any] | None = None
    install_result: dict[str, Any] | None = None
    cron_setup_result: dict[str, Any] | None = None

    if not dry_run:
        ok, note = run_bootstrap(
            script_path=bootstrap_py,
            projects_file=generated_projects_file,
            openclaw_home=openclaw_home,
            strict_remote=strict_remote,
            report_json=bootstrap_report_json,
            report_md=bootstrap_report_md,
        )
        bootstrap_result = {
            "ok": ok,
            "note": note,
            "report_json": str(bootstrap_report_json),
            "report_md": str(bootstrap_report_md),
        }

        if ok and install_index_job:
            job_ok, job_note = run_install_job(
                script_path=install_job_py,
                openclaw_home=openclaw_home,
                registry_file=registry_file,
                channel=args.job_channel.strip(),
                target=args.job_to.strip(),
            )
            install_result = {"ok": job_ok, "note": job_note}
        elif install_index_job:
            install_result = {"ok": False, "note": "bootstrap failed, skipped install_project_index_job"}

        if ok and install_cron_setup:
            cron_ok, cron_note = run_cron_setup(
                script_path=cron_setup_py,
                openclaw_home=openclaw_home,
                channel=args.cron_channel.strip(),
                target=args.cron_to.strip(),
                incremental_every_ms=int(args.cron_incremental_every_ms),
                full_expr=args.cron_full_expr.strip(),
                daily_expr=args.cron_daily_expr.strip(),
                daily_major_only=bool(args.cron_daily_major_only),
                incremental_log_mode=args.cron_incremental_log_mode,
                full_log_mode=args.cron_full_log_mode,
                daily_log_mode=args.cron_daily_log_mode,
                install_system_schedule_job=bool(install_system_schedule_job),
                system_log_mode=args.cron_system_log_mode,
                install_api_test_job=bool(install_api_test_job),
                api_test_expr=args.cron_api_test_expr.strip(),
                api_test_engine=args.cron_api_test_engine,
                api_test_log_mode=args.cron_api_test_log_mode,
                install_daily_work_job=bool(install_daily_work_job),
                daily_work_expr=args.cron_daily_work_expr.strip(),
                daily_work_log_mode=args.cron_daily_work_log_mode,
                dingtalk_webhook_env=args.cron_dingtalk_webhook_env.strip(),
                dingtalk_secret_env=args.cron_dingtalk_secret_env.strip(),
                install_self_evolution_job=bool(install_self_evolution_job),
                self_evolution_expr=args.cron_self_evolution_expr.strip(),
                self_evolution_log_mode=args.cron_self_evolution_log_mode,
                self_evolution_min_interval_days=int(args.cron_self_evolution_min_interval_days),
                self_evolution_max_tasks_per_run=int(args.cron_self_evolution_max_tasks_per_run),
            )
            cron_setup_result = {"ok": cron_ok, "note": cron_note}
        elif install_cron_setup:
            cron_setup_result = {"ok": False, "note": "bootstrap failed, skipped cron_setup"}

    setup_latest_json = setup_dir / "setup-latest.json"
    setup_latest_md = setup_dir / "setup-latest.md"
    result = {
        "ok": True,
        "mode": args.mode,
        "generated_at": now_iso(),
        "openclaw_home": str(openclaw_home),
        "task_center_dir": str(task_center_dir),
        "strict_git_remote": strict_remote,
        "dry_run": dry_run,
        "scan_roots": [str(x) for x in scan_roots],
        "selected_projects": [
            {
                "name": x.name,
                "path": str(x.path),
                "writable": x.writable,
                "git_repo": x.git_repo,
                "remote_url": x.remote_url,
                "remote_read_ok": x.remote_read_ok,
                "remote_push_ok": x.remote_push_ok,
                "deployment": x.deploy_plan,
                "hints": x.hints,
            }
            for x in assessments
        ],
        "generated_projects_file": str(generated_projects_file),
        "project_registry": str(registry_file),
        "bootstrap": bootstrap_result,
        "install_project_index_job": install_result,
        "install_cron_setup": cron_setup_result,
        "cron_setup_options": {
            "install_system_schedule_job": bool(install_system_schedule_job),
            "install_api_test_job": bool(install_api_test_job),
            "install_daily_work_job": bool(install_daily_work_job),
            "install_self_evolution_job": bool(install_self_evolution_job),
            "incremental_log_mode": args.cron_incremental_log_mode,
            "full_log_mode": args.cron_full_log_mode,
            "daily_log_mode": args.cron_daily_log_mode,
            "system_log_mode": args.cron_system_log_mode,
            "api_test_expr": args.cron_api_test_expr,
            "api_test_engine": args.cron_api_test_engine,
            "api_test_log_mode": args.cron_api_test_log_mode,
            "daily_work_expr": args.cron_daily_work_expr,
            "daily_work_log_mode": args.cron_daily_work_log_mode,
            "dingtalk_webhook_env": args.cron_dingtalk_webhook_env,
            "dingtalk_secret_env": args.cron_dingtalk_secret_env,
            "self_evolution_expr": args.cron_self_evolution_expr,
            "self_evolution_log_mode": args.cron_self_evolution_log_mode,
            "self_evolution_min_interval_days": int(args.cron_self_evolution_min_interval_days),
            "self_evolution_max_tasks_per_run": int(args.cron_self_evolution_max_tasks_per_run),
        },
        "reports": {
            "setup_json": str(setup_latest_json),
            "setup_md": str(setup_latest_md),
            "bootstrap_json": str(bootstrap_report_json),
            "bootstrap_md": str(bootstrap_report_md),
        },
    }
    setup_latest_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_markdown_report(
        path=setup_latest_md,
        mode=args.mode,
        openclaw_home=openclaw_home,
        strict_remote=strict_remote,
        dry_run=dry_run,
        selected=assessments,
        bootstrap_result=bootstrap_result,
        install_job_result=install_result,
        cron_setup_result=cron_setup_result,
    )

    if args.emit_json or not interactive:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("")
        print(f"Setup report: {setup_latest_md}")
        print(f"Registry: {registry_file}")
        if bootstrap_result:
            print(f"Bootstrap: {'ok' if bootstrap_result.get('ok') else 'failed'}")
        if install_result:
            print(f"Install index job: {'ok' if install_result.get('ok') else 'failed'}")
        if cron_setup_result:
            print(f"Install cron setup: {'ok' if cron_setup_result.get('ok') else 'failed'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

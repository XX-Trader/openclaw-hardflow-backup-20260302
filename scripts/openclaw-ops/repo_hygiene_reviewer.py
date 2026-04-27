#!/usr/bin/env python3
"""Read-only repository hygiene scanner.

The scanner reports cleanup candidates and creates a human-confirmed Task Center
candidate. It never deletes files or rewrites code by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_RUNTIME_HOME = (
    os.environ.get("HARDFLOW_RUNTIME_HOME")
    or os.environ.get("OPENCLAW_HOME")
    or os.environ.get("HERMES_HOME")
    or str(Path.home() / ".hardflow-runtime")
)
RUNTIME_HOME = Path(DEFAULT_RUNTIME_HOME).expanduser()
POLICY_DIR_CANDIDATES = [
    SCRIPT_PATH.parent / "policy",
    RUNTIME_HOME / "ops" / "policy",
    Path.home() / ".openclaw" / "ops" / "policy",
    SCRIPT_PATH.parents[2] / "skills" / "library" / "control-plane-ops" / "scripts" / "policy",
]
for candidate in POLICY_DIR_CANDIDATES:
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
        break

try:  # Task Center is optional for local dry-run tests.
    from task_center import TaskCenter, TaskCenterError  # type: ignore  # noqa: E402
except Exception:  # pragma: no cover - optional runtime boundary
    TaskCenter = None  # type: ignore

    class TaskCenterError(RuntimeError):
        pass


SKIP_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "sessions",
    "agent-workspaces",
    ".workflow",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
TEMP_SUFFIXES = (".tmp", ".orig", ".rej", ".pyc", ".pyo", ".swp")
TEXT_SUFFIXES = {".py", ".js", ".ts", ".json", ".md", ".txt", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh", ".ps1"}
MAX_TEXT_SCAN_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class HygieneFinding:
    category: str
    risk: str
    path: str
    reason: str
    suggested_action: str

    def as_dict(self) -> dict[str, str]:
        return {
            "category": self.category,
            "risk": self.risk,
            "path": self.path,
            "reason": self.reason,
            "suggested_action": self.suggested_action,
        }


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


def run_git(repo_path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_path),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def should_skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def rel_path(repo_path: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo_path)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def tracked_files(repo_path: Path) -> list[Path]:
    proc = run_git(repo_path, ["ls-files", "-z"])
    if proc.returncode == 0:
        files = [repo_path / item for item in proc.stdout.split("\0") if item]
        untracked = run_git(repo_path, ["ls-files", "-z", "--others", "--exclude-standard"])
        if untracked.returncode == 0:
            files.extend(repo_path / item for item in untracked.stdout.split("\0") if item)
        return sorted(
            {
                path
                for path in files
                if path.exists() and path.is_file() and not should_skip(path.relative_to(repo_path))
            }
        )
    out: list[Path] = []
    for cur, dirs, files in os.walk(repo_path):
        cur_path = Path(cur)
        dirs[:] = [name for name in dirs if name not in SKIP_PARTS]
        for name in files:
            path = cur_path / name
            if path.is_file() and not should_skip(path.relative_to(repo_path)):
                out.append(path)
    return sorted(out)


def cache_dirs(repo_path: Path, max_items: int) -> list[HygieneFinding]:
    out: list[HygieneFinding] = []
    cache_names = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage"}
    for cur, dirs, files in os.walk(repo_path):
        cur_path = Path(cur)
        for name in list(dirs) + list(files):
            if name not in cache_names:
                continue
            path = cur_path / name
            out.append(
                HygieneFinding(
                    category="generated_cache",
                    risk="low",
                    path=rel_path(repo_path, path),
                    reason="发现缓存或覆盖率生成物，通常不应长期留在仓库工作区。",
                    suggested_action="确认无运行中任务依赖后清理。",
                )
            )
            if len(out) >= max_items:
                return out
        dirs[:] = [name for name in dirs if name not in SKIP_PARTS and name not in cache_names]
    return out


def scan_git_conflicts(repo_path: Path) -> list[HygieneFinding]:
    proc = run_git(repo_path, ["status", "--porcelain"])
    if proc.returncode != 0:
        return []
    out: list[HygieneFinding] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        code = line[:2]
        if "U" not in code and code not in {"AA", "DD"}:
            continue
        out.append(
            HygieneFinding(
                category="git_conflict",
                risk="high",
                path=line[3:].strip(),
                reason=f"git status 显示未合并状态 {code}。",
                suggested_action="先人工确认冲突来源，再由 executor 修复并经过 code-reviewer 审查。",
            )
        )
    return out


def scan_text_conflict_markers(repo_path: Path, files: list[Path], max_findings: int) -> list[HygieneFinding]:
    out: list[HygieneFinding] = []
    for path in files:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_TEXT_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        has_start = False
        has_separator = False
        has_end = False
        for line in text.splitlines():
            has_start = has_start or line.startswith("<<<<<<< ")
            has_separator = has_separator or line == "======="
            has_end = has_end or line.startswith(">>>>>>> ")
        if has_start and has_separator and has_end:
            out.append(
                HygieneFinding(
                    category="conflict_marker",
                    risk="high",
                    path=rel_path(repo_path, path),
                    reason="文件中存在 Git 冲突标记。",
                    suggested_action="人工确认后修复冲突，并运行相关测试。",
                )
            )
            if len(out) >= max_findings:
                break
    return out


def scan_temp_files(repo_path: Path, files: list[Path], max_findings: int) -> list[HygieneFinding]:
    out: list[HygieneFinding] = []
    for path in files:
        name = path.name.lower()
        if not (name.endswith(TEMP_SUFFIXES) or ".bak." in name or name.endswith(".bak") or name.endswith("~")):
            continue
        out.append(
            HygieneFinding(
                category="temporary_or_backup_file",
                risk="low",
                path=rel_path(repo_path, path),
                reason="疑似临时、备份或冲突残留文件。",
                suggested_action="确认不是事实源后删除；删除操作需进入正常流水线。",
            )
        )
        if len(out) >= max_findings:
            break
    return out


def scan_duplicate_files(repo_path: Path, files: list[Path], max_findings: int) -> list[HygieneFinding]:
    buckets: dict[tuple[str, int, str], list[Path]] = {}
    for path in files:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size == 0 or size > 512 * 1024:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        buckets.setdefault((path.name.lower(), size, digest), []).append(path)

    out: list[HygieneFinding] = []
    for (_name, _size, _digest), group in sorted(buckets.items(), key=lambda item: item[0][0]):
        if len(group) < 2:
            continue
        rels = [rel_path(repo_path, item) for item in group]
        out.append(
            HygieneFinding(
                category="duplicate_file",
                risk="medium",
                path=", ".join(rels[:5]),
                reason="多个同名文本文件内容完全一致，可能是冗余副本。",
                suggested_action="由 optimization-agent/code-simplifier 判断保留唯一事实源，删除前必须经 code-reviewer 审核。",
            )
        )
        if len(out) >= max_findings:
            break
    return out


def scan_repo(repo_path: Path, max_findings: int = 80) -> list[HygieneFinding]:
    files = tracked_files(repo_path)
    findings: list[HygieneFinding] = []
    findings.extend(scan_git_conflicts(repo_path))
    findings.extend(scan_text_conflict_markers(repo_path, files, max_findings))
    findings.extend(scan_temp_files(repo_path, files, max_findings))
    findings.extend(scan_duplicate_files(repo_path, files, max_findings))
    findings.extend(cache_dirs(repo_path, max_findings))
    unique: list[HygieneFinding] = []
    seen: set[tuple[str, str, str]] = set()
    for item in findings:
        key = (item.category, item.path, item.reason)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= max_findings:
            break
    return unique


def render_report(repo_path: Path, findings: list[HygieneFinding]) -> str:
    counts: dict[str, int] = {}
    for item in findings:
        counts[item.category] = counts.get(item.category, 0) + 1
    lines = [
        "# 仓库精简巡检报告",
        "",
        f"- 仓库: {repo_path}",
        f"- 生成时间: {utc_now()}",
        f"- 发现数量: {len(findings)}",
        "- 执行边界: 只读扫描，不删除文件，不修改代码，不提交 Git。",
        "",
        "## 分类统计",
    ]
    if counts:
        for category, count in sorted(counts.items()):
            lines.append(f"- {category}: {count}")
    else:
        lines.append("- 无清理候选")
    lines.extend(["", "## 发现明细"])
    if not findings:
        lines.append("- 本次未发现需要处理的仓库精简候选。")
    for index, item in enumerate(findings, start=1):
        lines.extend(
            [
                f"### {index}. {item.category}",
                f"- 风险: {item.risk}",
                f"- 路径: `{item.path}`",
                f"- 原因: {item.reason}",
                f"- 建议: {item.suggested_action}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_report(output_dir: Path, repo_path: Path, findings: list[HygieneFinding]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = output_dir / f"repo_hygiene_{stamp}.md"
    report_path.write_text(render_report(repo_path, findings), encoding="utf-8")
    return report_path


def finding_fingerprint(repo_path: Path, findings: list[HygieneFinding]) -> str:
    payload = {
        "repo": str(repo_path.resolve()),
        "findings": [item.as_dict() for item in findings],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def create_task_candidate(
    *,
    task_db: Path,
    task_id_base: str,
    repo_path: Path,
    report_path: Path,
    findings: list[HygieneFinding],
    actor: str,
    assignee: str,
) -> dict[str, Any]:
    if TaskCenter is None:
        return {"created": [], "existing": [], "error": "task_center_unavailable"}
    if not findings:
        return {"created": [], "existing": []}
    fingerprint = finding_fingerprint(repo_path, findings)
    task_id = f"{task_id_base}:{fingerprint}"
    high_risk = any(item.risk == "high" for item in findings)
    payload = {
        "task_id": task_id,
        "pool": "jobs",
        "task_type": "repo_hygiene_candidate",
        "reason": f"仓库精简巡检发现 {len(findings)} 个候选项",
        "source": "repo-hygiene-reviewer",
        "request_source": "human",
        "priority": "high" if high_risk else "medium",
        "risk_level": "high" if high_risk else "low",
        "assignee": assignee,
        "status": "pending",
        "need_human_confirm": True,
        "human_confirmed": False,
        "action": "await_human_confirm",
        "requirement": "请确认仓库精简巡检报告中的候选项，确认后再由 optimization-agent/code-simplifier 分小批次清理。",
        "result_output": "人工确认后的清理任务、拒绝记录或澄清要求。",
        "acceptance": "删除或重构必须经过测试和 code-reviewer 审核；高风险项不得由定时任务自动处理。",
        "observable_outputs": str(report_path),
        "acceptance_thresholds": "need_human_confirm=true 时不得自动执行删除或 Git 发布。",
        "context_payload": {
            "repo_path": str(repo_path),
            "report_path": str(report_path),
            "finding_count": len(findings),
            "findings": [item.as_dict() for item in findings[:20]],
        },
        "allowed_agents": ["human-inbox", "optimization-agent", "code-simplifier", "code-reviewer"],
        "required_capabilities": ["code_simplification", "repository_hygiene", "human_confirmation"],
        "required_skills": ["project-delivery-pipeline"],
    }
    center = TaskCenter(task_db)
    try:
        center.init_schema()
        try:
            center.get_task(task_id, display_safe=False)
        except TaskCenterError:
            created = center.create_task(payload, actor=actor)
            return {"created": [created["task_id"]], "existing": []}
        return {"created": [], "existing": [task_id]}
    finally:
        center.close()


def run_review(
    *,
    repo_path: Path,
    output_dir: Path,
    task_db: Path | None = None,
    task_id: str = "cron:repo-hygiene-reviewer",
    actor: str = "optimization-agent",
    assignee: str = "human-inbox",
    max_findings: int = 80,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo_path = repo_path.expanduser().resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise FileNotFoundError(f"repo path not found: {repo_path}")
    findings = scan_repo(repo_path, max_findings=max(1, int(max_findings or 80)))
    report_path = write_report(output_dir.expanduser().resolve(), repo_path, findings)
    task_summary: dict[str, Any] = {"created": [], "existing": []}
    if task_db is not None and findings and not dry_run:
        task_summary = create_task_candidate(
            task_db=task_db.expanduser().resolve(),
            task_id_base=task_id,
            repo_path=repo_path,
            report_path=report_path,
            findings=findings,
            actor=actor,
            assignee=assignee,
        )
    return {
        "repo_path": str(repo_path),
        "report_path": str(report_path),
        "finding_count": len(findings),
        "findings": [item.as_dict() for item in findings],
        "task_center": task_summary,
        "dry_run": dry_run,
    }


def default_task_db() -> Path:
    return RUNTIME_HOME / "ops" / "task-center" / "task_center.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只读仓库精简巡检器")
    parser.add_argument("--repo-path", default=os.environ.get("HARDFLOW_WORKFLOW_REPO", "."))
    parser.add_argument("--output-dir", default=str(RUNTIME_HOME / "ops" / "repo-hygiene"))
    parser.add_argument("--task-db", default=str(default_task_db()))
    parser.add_argument("--task-id", default="cron:repo-hygiene-reviewer")
    parser.add_argument("--actor", default="optimization-agent")
    parser.add_argument("--assignee", default="human-inbox")
    parser.add_argument("--max-findings", type=int, default=80)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--emit-json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_review(
            repo_path=Path(args.repo_path),
            output_dir=Path(args.output_dir),
            task_db=Path(args.task_db) if str(args.task_db).strip() else None,
            task_id=str(args.task_id or "cron:repo-hygiene-reviewer"),
            actor=str(args.actor or "optimization-agent"),
            assignee=str(args.assignee or "human-inbox"),
            max_findings=int(args.max_findings),
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:  # pragma: no cover - CLI safety net
        print(f"FAILED repo_hygiene_reviewer: {exc}", file=sys.stderr)
        return 2

    if args.emit_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    if summary["finding_count"] == 0:
        print("NO_REPLY")
        return 0
    task_center = summary.get("task_center", {})
    print(
        "repo_hygiene_reviewer "
        f"findings={summary['finding_count']} "
        f"created={len(task_center.get('created', []))} "
        f"existing={len(task_center.get('existing', []))} "
        f"report={summary['report_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Local git backup runner for ~/.openclaw (commit only, no push)."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utf8_runtime import configure_process_utf8_stdio

configure_process_utf8_stdio()

UTC = timezone.utc
LOG_MODES = {"silent", "chat"}
NOTIFY_MODES = {"errors-only", "on-change", "always"}

# NOTE: 不再使用白名单（include prefix），改为纯黑名单模式。
# 所有不在 DEFAULT_EXCLUDE_GLOBS 中的文件都会自动纳入备份。

DEFAULT_EXCLUDE_GLOBS = (
    "**/.git/**",
    ".git/**",
    "**/.locks/**",
    "ops/.locks/**",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
    "ops/cron-backup/**",
    "ops/*-runs/**",
    "ops/*-reports/**",
    "ops/*/reports/**",
    "ops/task-center/**/*.db*",
    "ops/task-center/*.db*",
    "ops/task-center/*.sqlite*",
    "workspace-*/logs/**",
    "workspace-*/sessions/**",
    "workspace-*/downloads/**",
    "workspace-*/tmp/**",
    "workspace-*/.codex/**",
    "agents/*/sessions/**",
    "agents/*/sessions.json",
    "cron/runs/**",
    "cron/jobs.json.bak*",
    "openclaw.json.bak*",
    "browser/**",
    "*.log",
    "**/*.log",
)

DEFAULT_GITIGNORE_LINES = (
    "# openclaw local backup (auto)",
    "*.log",
    "**/*.log",
    ".DS_Store",
    "Thumbs.db",
    "**/.locks/",
    "ops/cron-backup/",
    "__pycache__/",
    "*.pyc",
    "ops/*-runs/",
    "ops/*-reports/",
    "ops/task-center/*.db*",
    "workspace-*/logs/",
    "workspace-*/sessions/",
    "workspace-*/downloads/",
    "workspace-*/tmp/",
    "workspace-*/.codex/",
    "agents/*/sessions/",
    "cron/runs/",
    "cron/jobs.json.bak*",
    "openclaw.json.bak*",
    "browser/",
)


def now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def normalize_log_mode(value: str, default: str = "silent") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in LOG_MODES else default


def normalize_notify_mode(value: str, default: str = "errors-only") -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in NOTIFY_MODES else default


def normalize_rel(path: str) -> str:
    text = str(path or "").replace("\\", "/").lstrip("/")
    while text.startswith("./"):
        text = text[2:]
    return text


def run_git(repo: Path, args: list[str], *, timeout: int = 60) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=max(5, int(timeout)),
            check=False,
        )
    except Exception as exc:
        return 127, "", str(exc)
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def parse_status_porcelain_z(raw: str) -> list[dict[str, str]]:
    """Parse git status --porcelain=v1 -z output into [{status, path}].

    FIX: run_git() 对 stdout 做了 .strip()，会吃掉 porcelain v1 格式
    的前导空格（' M path' → 'M path'），导致 token[3:] 截断路径首字符。
    这里检测并恢复被 strip 掉的前导空格。
    """
    out: list[dict[str, str]] = []
    text = str(raw or "")
    # porcelain v1 每项格式: 'XY path'，X/Y 各一字符，第3字符为空格。
    # 如果 .strip() 移除了前导空格（即 X 为空格时），需要恢复。
    if text and len(text) >= 3 and text[0] in "MADRCU?!" and text[1] == " ":
        text = " " + text
    items = text.split("\0")
    idx = 0
    while idx < len(items):
        token = items[idx]
        idx += 1
        if not token:
            continue
        if len(token) < 4:
            continue
        status = token[:2]
        path = normalize_rel(token[3:])
        if status and ("R" in status or "C" in status) and idx < len(items):
            renamed = normalize_rel(items[idx])
            idx += 1
            if renamed:
                out.append({"status": status, "path": renamed})
            continue
        if path:
            out.append({"status": status, "path": path})
    return out


def matches_any_glob(path: str, patterns: list[str]) -> bool:
    rel = normalize_rel(path)
    for pattern in patterns:
        p = normalize_rel(pattern)
        if not p:
            continue
        if fnmatch.fnmatch(rel, p):
            return True
    return False


def startswith_any(path: str, prefixes: list[str]) -> bool:
    rel = normalize_rel(path).lower()
    for prefix in prefixes:
        p = normalize_rel(prefix).lower()
        if p and rel.startswith(p):
            return True
    return False


def should_include(
    path: str,
    *,
    include_prefixes: list[str],
    exclude_prefixes: list[str],
    include_globs: list[str],
    exclude_globs: list[str],
) -> bool:
    """纯黑名单模式：只要不在排除列表中，就纳入备份。

    Args:
        path: 相对路径
        include_prefixes: 保留参数兼容性，当前不影响排除逻辑
        exclude_prefixes: 按前缀排除的列表
        include_globs: 保留参数兼容性，当前不影响排除逻辑
        exclude_globs: 按 glob 模式排除的列表

    Returns:
        True 表示应该纳入备份
    """
    rel = normalize_rel(path)
    if not rel:
        return False
    if startswith_any(rel, exclude_prefixes):
        return False
    if matches_any_glob(rel, exclude_globs):
        return False
    return True


def chunked(values: list[str], size: int) -> list[list[str]]:
    out: list[list[str]] = []
    step = max(1, int(size))
    for idx in range(0, len(values), step):
        out.append(values[idx : idx + step])
    return out


def ensure_repo_ready(repo: Path, *, author_name: str, author_email: str) -> tuple[bool, list[str], bool]:
    errors: list[str] = []
    initialized = False
    if not repo.exists() or (not repo.is_dir()):
        return False, [f"repo_invalid:{repo}"], initialized

    if not (repo / ".git").exists():
        rc, _out, err = run_git(repo, ["init", "-b", "main"], timeout=30)
        if rc != 0:
            rc2, _out2, err2 = run_git(repo, ["init"], timeout=30)
            if rc2 != 0:
                return False, [f"git_init_failed:{err or err2 or rc}"], initialized
            run_git(repo, ["checkout", "-B", "main"], timeout=30)
        initialized = True

    rc, out, err = run_git(repo, ["rev-parse", "--is-inside-work-tree"], timeout=20)
    if rc != 0 or str(out).strip().lower() != "true":
        return False, [f"not_git_repo:{err or out or repo}"], initialized

    rc_name, name_out, _err_name = run_git(repo, ["config", "--get", "user.name"], timeout=20)
    rc_mail, mail_out, _err_mail = run_git(repo, ["config", "--get", "user.email"], timeout=20)
    if rc_name != 0 or not str(name_out).strip():
        rc_set_name, _out_set_name, err_set_name = run_git(repo, ["config", "user.name", author_name], timeout=20)
        if rc_set_name != 0:
            errors.append(f"git_config_user_name_failed:{err_set_name or rc_set_name}")
    if rc_mail != 0 or not str(mail_out).strip():
        rc_set_mail, _out_set_mail, err_set_mail = run_git(repo, ["config", "user.email", author_email], timeout=20)
        if rc_set_mail != 0:
            errors.append(f"git_config_user_email_failed:{err_set_mail or rc_set_mail}")
    return len(errors) == 0, errors, initialized


def ensure_gitignore(repo: Path) -> bool:
    p = repo / ".gitignore"
    existing = p.read_text(encoding="utf-8", errors="ignore").splitlines() if p.exists() else []
    seen = {line.strip() for line in existing}
    changed = False
    for line in DEFAULT_GITIGNORE_LINES:
        if line.strip() not in seen:
            existing.append(line)
            seen.add(line.strip())
            changed = True
    if changed:
        p.write_text("\n".join(existing).rstrip() + "\n", encoding="utf-8")
    return changed


def humanize_error(error: str) -> tuple[str, str]:
    text = str(error or "").strip()
    if ":" in text:
        code, detail = text.split(":", 1)
    else:
        code, detail = text, ""
    detail = detail.strip()
    mapping = {
        "repo_invalid": "仓库路径无效",
        "git_init_failed": "Git 仓库初始化失败",
        "not_git_repo": "仓库不是有效的 Git 仓库",
        "git_config_user_name_failed": "Git 用户名配置失败",
        "git_config_user_email_failed": "Git 邮箱配置失败",
        "git_status_failed": "Git 状态读取失败",
        "git_add_failed": "Git 暂存文件失败",
        "git_diff_cached_failed": "Git 暂存差异读取失败",
        "git_commit_failed": "Git 提交失败",
    }
    return mapping.get(code, "本地 Git 备份执行失败"), detail or text


def build_chat_output(
    result: dict[str, Any],
    notify_mode: str,
    *,
    list_changed_files: bool = False,
    max_listed_files: int = 20,
) -> str:
    if result["errors"]:
        lines = [
            "本地 Git 备份异常",
            f"- 任务: {result['task_id'] or '-'}",
            f"- 时间: {result['time']}",
            f"- 仓库: {result['repo']}",
            f"- 初始化仓库: {'是' if result['initialized'] else '否'}",
            f"- 更新.gitignore: {'是' if result['gitignore_updated'] else '否'}",
            f"- 已提交: {'是' if result['committed'] else '否'}",
            f"- 可处理文件数: {len(result['eligible_files'])}",
            f"- 已跳过文件数: {len(result['skipped_files'])}",
            f"- 异常数量: {len(result['errors'])}",
        ]
        for idx, err in enumerate(result["errors"][:10], start=1):
            title, detail = humanize_error(err)
            lines.append(f"- 异常{idx}: {title}")
            lines.append(f"- 详情{idx}: {detail}")
        return "\n".join(lines)

    if notify_mode not in {"always", "on-change"}:
        return "NO_REPLY"
    if notify_mode == "on-change" and not (
        result["committed"] or result["initialized"] or result["gitignore_updated"]
    ):
        return "NO_REPLY"

    lines = [
        "本地 Git 备份",
        f"- 任务: {result['task_id'] or '-'}",
        f"- 时间: {result['time']}",
        f"- 仓库: {result['repo']}",
        f"- 初始化仓库: {'是' if result['initialized'] else '否'}",
        f"- 更新.gitignore: {'是' if result['gitignore_updated'] else '否'}",
        f"- 已提交: {'是' if result['committed'] else '否'}",
        f"- 可处理文件数: {len(result['eligible_files'])}",
        f"- 已跳过文件数: {len(result['skipped_files'])}",
        f"- 通知模式: {notify_mode}",
    ]
    if str(result.get("commit_sha", "")).strip():
        lines.append(f"- 提交: {result['commit_sha']}")
    if list_changed_files:
        max_count = max(0, int(max_listed_files))
        for path in result["eligible_files"][:max_count]:
            lines.append(f"- 变更: {path}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local git backup runner (commit only, no push)")
    parser.add_argument("--repo-path", default=str(Path.home() / ".openclaw"))
    parser.add_argument("--task-id", default="")
    parser.add_argument("--normal-log-mode", default="silent", choices=sorted(LOG_MODES))
    parser.add_argument("--notify-on", default="errors-only", choices=sorted(NOTIFY_MODES))
    parser.add_argument("--list-changed-files", action="store_true")
    parser.add_argument("--max-listed-files", type=int, default=20)
    parser.add_argument("--author-name", default="openclaw-local-backup")
    parser.add_argument("--author-email", default="openclaw@local")
    parser.add_argument("--commit-prefix", default="chore(local-backup): snapshot ~/.openclaw")
    parser.add_argument("--commit-message", default="")
    parser.add_argument("--include-prefix", action="append", default=[])
    parser.add_argument("--exclude-prefix", action="append", default=[])
    parser.add_argument("--include-glob", action="append", default=[])
    parser.add_argument("--exclude-glob", action="append", default=[])
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--emit-json", action="store_true")
    args = parser.parse_args()

    repo = Path(str(args.repo_path or ".")).expanduser().resolve()
    log_mode = normalize_log_mode(args.normal_log_mode, default="silent")
    notify_mode = normalize_notify_mode(args.notify_on, default="errors-only")
    include_prefixes = [normalize_rel(x) for x in args.include_prefix if str(x).strip()]
    exclude_prefixes = [normalize_rel(x) for x in args.exclude_prefix if str(x).strip()]
    include_globs = [normalize_rel(x) for x in args.include_glob if str(x).strip()]
    exclude_globs = [normalize_rel(x) for x in args.exclude_glob if str(x).strip()]
    # 纯黑名单模式：include_prefixes / include_globs 保留 CLI 兼容性但不再有默认值
    if not exclude_globs:
        exclude_globs = [normalize_rel(x) for x in DEFAULT_EXCLUDE_GLOBS]

    result: dict[str, Any] = {
        "time": now_iso(),
        "task_id": str(args.task_id or "").strip(),
        "repo": str(repo),
        "normal_log_mode": log_mode,
        "notify_on": notify_mode,
        "initialized": False,
        "gitignore_updated": False,
        "committed": False,
        "commit_sha": "",
        "eligible_files": [],
        "skipped_files": [],
        "errors": [],
    }

    ok, errors, initialized = ensure_repo_ready(
        repo,
        author_name=str(args.author_name or "openclaw-local-backup").strip() or "openclaw-local-backup",
        author_email=str(args.author_email or "openclaw@local").strip() or "openclaw@local",
    )
    result["initialized"] = initialized
    if not ok:
        result["errors"].extend(errors)

    if not result["errors"]:
        result["gitignore_updated"] = ensure_gitignore(repo)

    if not result["errors"]:
        rc, status_out, err = run_git(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"], timeout=30)
        if rc != 0:
            result["errors"].append(f"git_status_failed:{err or rc}")
        else:
            changes = parse_status_porcelain_z(status_out)
            eligible: list[str] = []
            skipped: list[str] = []
            for item in changes:
                path = str(item.get("path", "")).strip()
                if should_include(
                    path,
                    include_prefixes=include_prefixes,
                    exclude_prefixes=exclude_prefixes,
                    include_globs=include_globs,
                    exclude_globs=exclude_globs,
                ):
                    eligible.append(path)
                else:
                    skipped.append(path)
            max_files = max(1, int(args.max_files))
            if len(eligible) > max_files:
                skipped.extend(eligible[max_files:])
                eligible = eligible[:max_files]
            result["eligible_files"] = sorted(set(eligible))
            result["skipped_files"] = sorted(set(skipped))

    if not result["errors"] and result["eligible_files"]:
        # 使用 git add -u 只更新已跟踪文件，避免逐个 add 导致的性能问题
        rc, _out, err = run_git(repo, ["add", "-u"], timeout=120)
        if rc != 0:
            result["errors"].append(f"git_add_failed:{err or rc}")


    if not result["errors"] and result["eligible_files"]:
        rc, staged_out, err = run_git(repo, ["diff", "--cached", "--name-only"], timeout=20)
        if rc != 0:
            result["errors"].append(f"git_diff_cached_failed:{err or rc}")
        elif not str(staged_out).strip():
            result["eligible_files"] = []
        else:
            commit_message = str(args.commit_message or "").strip()
            if not commit_message:
                commit_prefix = str(args.commit_prefix or "").strip() or "chore(local-backup): snapshot ~/.openclaw"
                ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
                task_suffix = f" [{result['task_id']}]" if result["task_id"] else ""
                commit_message = f"{commit_prefix}{task_suffix} ({ts})"
            rc, _out, err = run_git(repo, ["commit", "-m", commit_message], timeout=120)
            if rc != 0:
                result["errors"].append(f"git_commit_failed:{err or rc}")
            else:
                result["committed"] = True
                rc2, sha, _err2 = run_git(repo, ["rev-parse", "HEAD"], timeout=20)
                if rc2 == 0 and str(sha).strip():
                    result["commit_sha"] = str(sha).strip()

    notify = False
    if notify_mode == "always":
        notify = True
    elif notify_mode == "on-change":
        notify = bool(result["errors"]) or bool(result["committed"]) or bool(result["initialized"]) or bool(
            result["gitignore_updated"]
        )
    else:
        notify = bool(result["errors"])

    output = (
        build_chat_output(
            result,
            notify_mode,
            list_changed_files=bool(args.list_changed_files),
            max_listed_files=max(0, int(args.max_listed_files or 0)),
        )
        if notify
        else "NO_REPLY"
    )

    if bool(args.emit_json):
        print(json.dumps({"notify": notify, "output": output, "result": result}, ensure_ascii=False))
    else:
        print(output if notify else "NO_REPLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

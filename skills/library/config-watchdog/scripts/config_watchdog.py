#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
config_watchdog.py — 配置文件安全看门狗

监控关键配置文件的变更，执行前置校验，自动备份，变更异常时告警。
核心防御对象：openclaw.json / cron/jobs.json / agents/*/SOUL.md

用法:
    python config_watchdog.py --help
    python config_watchdog.py --config-dir ~/.openclaw/ --dry-run
    python config_watchdog.py --config-dir ~/.openclaw/ --snapshot
    python config_watchdog.py --config-dir ~/.openclaw/ --verify
    python config_watchdog.py --config-dir ~/.openclaw/ --rollback --target openclaw.json
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path


def configure_process_utf8_stdio():
    """确保 stdout/stderr 使用 UTF-8 编码，避免中文乱码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ──────────────────────────────────────────────
# 关注配置文件
# ──────────────────────────────────────────────

DEFAULT_WATCHED_FILES = [
    "openclaw.json",
    "cron/jobs.json",
    "hooks/hardflow-audit/handler.js",
    "hooks/hardflow-failure-detector/handler.js",
]

DEFAULT_WATCHED_PATTERNS = [
    "agents/*/SOUL.md",
]

SNAPSHOT_DIR_NAME = ".config-watchdog-snapshots"


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def compute_file_hash(file_path):
    """
    计算文件的 SHA-256 哈希。

    Args:
        file_path: 文件路径。

    Returns:
        str: 文件的 SHA-256 十六进制哈希值，文件不存在返回 None。
    """
    target_path = Path(file_path)
    if not target_path.exists():
        return None
    sha256 = hashlib.sha256()
    with open(target_path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def resolve_watched_files(config_dir):
    """
    解析所有需要监控的配置文件。

    Args:
        config_dir: 配置根目录。

    Returns:
        list[Path]: 解析后的文件路径列表。
    """
    config_root = Path(config_dir)
    watched = []

    for relative_path in DEFAULT_WATCHED_FILES:
        full_path = config_root / relative_path
        if full_path.exists():
            watched.append(full_path)

    for pattern in DEFAULT_WATCHED_PATTERNS:
        for matched_file in config_root.glob(pattern):
            if matched_file.is_file():
                watched.append(matched_file)

    return sorted(set(watched))


# ──────────────────────────────────────────────
# 快照
# ──────────────────────────────────────────────

def take_snapshot(config_dir, backup_dir=None):
    """
    对所有监控文件取快照（备份 + hash 记录）。

    Args:
        config_dir: 配置根目录。
        backup_dir: 快照存储目录，默认在 config_dir/.config-watchdog-snapshots/。

    Returns:
        dict: 快照结果（snapshot_id / files / hashes）。
    """
    config_root = Path(config_dir)
    if not backup_dir:
        snapshot_base = config_root / SNAPSHOT_DIR_NAME
    else:
        snapshot_base = Path(backup_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_id = f"snapshot-{timestamp}"
    snapshot_dir = snapshot_base / snapshot_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    watched_files = resolve_watched_files(config_dir)
    hashes = {}
    file_count = 0

    for watched_file in watched_files:
        relative = watched_file.relative_to(config_root)
        dest = snapshot_dir / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(watched_file), str(dest))
        hashes[str(relative)] = compute_file_hash(watched_file)
        file_count += 1

    # 写入 hash manifest
    manifest = {
        "snapshot_id": snapshot_id,
        "timestamp": datetime.now().isoformat(),
        "config_dir": str(config_root),
        "file_count": file_count,
        "hashes": hashes,
    }
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    # 清理旧快照（保留最近 10 个）
    existing_snapshots = sorted(snapshot_base.glob("snapshot-*"), key=lambda p: p.name, reverse=True)
    for old_snapshot in existing_snapshots[10:]:
        shutil.rmtree(str(old_snapshot), ignore_errors=True)

    return manifest


# ──────────────────────────────────────────────
# 变更验证
# ──────────────────────────────────────────────

def verify_against_snapshot(config_dir, backup_dir=None):
    """
    将当前配置与最新快照对比，检测变更。

    Args:
        config_dir: 配置根目录。
        backup_dir: 快照存储目录。

    Returns:
        dict: 验证结果（status / changed / added / deleted / unchanged）。
    """
    config_root = Path(config_dir)
    if not backup_dir:
        snapshot_base = config_root / SNAPSHOT_DIR_NAME
    else:
        snapshot_base = Path(backup_dir)

    # 找到最新快照
    snapshots = sorted(snapshot_base.glob("snapshot-*"), key=lambda p: p.name, reverse=True)
    if not snapshots:
        return {"status": "no_snapshot", "detail": "无历史快照可对比，请先执行 --snapshot"}

    latest_snapshot = snapshots[0]
    manifest_path = latest_snapshot / "manifest.json"
    if not manifest_path.exists():
        return {"status": "corrupt_snapshot", "detail": f"快照 {latest_snapshot.name} 缺少 manifest.json"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_hashes = manifest.get("hashes", {})

    # 计算当前 hash
    watched_files = resolve_watched_files(config_dir)
    current_hashes = {}
    for watched_file in watched_files:
        relative = str(watched_file.relative_to(config_root))
        current_hashes[relative] = compute_file_hash(watched_file)

    # 对比
    changed = []
    added = []
    deleted = []
    unchanged = []

    all_keys = set(list(old_hashes.keys()) + list(current_hashes.keys()))
    for key in sorted(all_keys):
        old_hash = old_hashes.get(key)
        new_hash = current_hashes.get(key)

        if old_hash and not new_hash:
            deleted.append(key)
        elif not old_hash and new_hash:
            added.append(key)
        elif old_hash != new_hash:
            changed.append(key)
        else:
            unchanged.append(key)

    has_changes = bool(changed or added or deleted)
    return {
        "status": "changes_detected" if has_changes else "no_changes",
        "snapshot_id": manifest.get("snapshot_id"),
        "snapshot_timestamp": manifest.get("timestamp"),
        "changed": changed,
        "added": added,
        "deleted": deleted,
        "unchanged": unchanged,
        "total_monitored": len(all_keys),
    }


# ──────────────────────────────────────────────
# JSON 前置校验
# ──────────────────────────────────────────────

def validate_json_file(file_path):
    """
    验证 JSON 文件的语法正确性。

    Args:
        file_path: 文件路径。

    Returns:
        dict: 验证结果（valid / error）。
    """
    target = Path(file_path)
    if not target.exists():
        return {"valid": False, "error": f"文件不存在: {file_path}"}

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        json.loads(content)
        return {"valid": True, "error": None}
    except json.JSONDecodeError as json_error:
        return {"valid": False, "error": f"JSON 语法错误 L{json_error.lineno}:{json_error.colno} — {json_error.msg}"}


def validate_openclaw_config(file_path):
    """
    对 openclaw.json 执行业务级校验：
    - 所有引用的 agent 目录必须存在
    - 所有引用的 hook handler 文件必须存在
    - model 配置不能为空

    Args:
        file_path: openclaw.json 的路径。

    Returns:
        dict: 验证结果（valid / errors / warnings）。
    """
    target = Path(file_path)
    config_dir = target.parent

    json_validation = validate_json_file(file_path)
    if not json_validation["valid"]:
        return {"valid": False, "errors": [json_validation["error"]], "warnings": []}

    content = json.loads(target.read_text(encoding="utf-8"))
    errors = []
    warnings = []

    # 检查 agents
    agents_config = content.get("agents", {})
    agent_list = agents_config.get("list", [])
    for agent in agent_list:
        agent_name = agent.get("name", "unknown")
        # 优先使用 id / agent_id 作为目录名，回退到 name
        agent_dir = (
            str(agent.get("id", "") or "").strip()
            or str(agent.get("agent_id", "") or "").strip()
            or agent_name
        )
        soul_path = config_dir / "agents" / agent_dir / "SOUL.md"
        if not soul_path.exists():
            errors.append(f"Agent '{agent_name}' (dir={agent_dir}) 的 SOUL.md 不存在: {soul_path}")

    # 检查 hooks — 兼容 list[dict] 和 dict 两种配置格式
    hooks_config = content.get("hooks", [])
    hooks_list: list[dict] = []
    if isinstance(hooks_config, list):
        hooks_list = [h for h in hooks_config if isinstance(h, dict)]
    elif isinstance(hooks_config, dict):
        # dict 格式 (如 {"internal": {"enabled": true, "load": {...}}})
        # 不包含顶层 handler 路径，遍历子项中的 handler
        for hook_name, hook_value in hooks_config.items():
            if isinstance(hook_value, dict):
                hooks_list.append(hook_value)
    for hook in hooks_list:
        handler_path_str = hook.get("handler", "")
        if handler_path_str:
            handler_path = config_dir / handler_path_str
            if not handler_path.exists():
                errors.append(f"Hook handler 不存在: {handler_path_str}")

    # 检查 models
    models_config = content.get("models", {})
    if not models_config:
        warnings.append("models 配置为空，所有 Agent 将使用默认模型")

    is_valid = len(errors) == 0
    return {"valid": is_valid, "errors": errors, "warnings": warnings}


# ──────────────────────────────────────────────
# 回滚
# ──────────────────────────────────────────────

def rollback_file(config_dir, target_relative_path, backup_dir=None, dry_run=False):
    """
    从最新快照恢复指定配置文件。

    Args:
        config_dir: 配置根目录。
        target_relative_path: 要恢复的文件相对路径。
        backup_dir: 快照目录。
        dry_run: 仅报告不执行。

    Returns:
        dict: 回滚结果（status / detail）。
    """
    config_root = Path(config_dir)
    if not backup_dir:
        snapshot_base = config_root / SNAPSHOT_DIR_NAME
    else:
        snapshot_base = Path(backup_dir)

    snapshots = sorted(snapshot_base.glob("snapshot-*"), key=lambda p: p.name, reverse=True)
    if not snapshots:
        return {"status": "failed", "detail": "无可用快照，无法回滚"}

    latest_snapshot = snapshots[0]
    backup_file = latest_snapshot / target_relative_path

    if not backup_file.exists():
        return {"status": "failed", "detail": f"快照中未找到 {target_relative_path}"}

    target_file = config_root / target_relative_path

    if not dry_run:
        # 先备份当前（损坏的）版本
        if target_file.exists():
            broken_backup = target_file.with_suffix(target_file.suffix + f".broken-{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            shutil.copy2(str(target_file), str(broken_backup))

        shutil.copy2(str(backup_file), str(target_file))

    return {
        "status": "rolled_back",
        "detail": f"已从 {latest_snapshot.name} 恢复 {target_relative_path}",
        "snapshot_used": latest_snapshot.name,
        "dry_run": dry_run,
    }


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def run_watchdog(config_dir, action="verify", target=None, backup_dir=None, dry_run=False, task_id=None):
    """
    执行配置看门狗的主流程。

    Args:
        config_dir: 配置根目录。
        action: 执行动作（"snapshot" / "verify" / "rollback" / "validate"）。
        target: 回滚目标文件路径。
        backup_dir: 快照存储目录。
        dry_run: 仅报告。
        task_id: 任务 ID。

    Returns:
        dict: 执行结果。
    """
    config_root = Path(config_dir)
    if not config_root.exists():
        print(f"❌ 配置目录不存在: {config_dir}", file=sys.stderr)
        return {"error": f"配置目录不存在: {config_dir}"}

    if action == "snapshot":
        result = take_snapshot(config_dir, backup_dir)
        print(f"✅ 快照已创建: {result['snapshot_id']} ({result['file_count']} 文件)")
        return result

    elif action == "verify":
        result = verify_against_snapshot(config_dir, backup_dir)

        if result["status"] == "no_snapshot":
            print(f"⚠️ {result['detail']}")
            return result

        if result["status"] == "no_changes":
            print(f"✅ 配置无变更（对比快照 {result['snapshot_id']}）")
        else:
            print(f"⚠️ 检测到配置变更!")
            if result["changed"]:
                print(f"  📝 已修改: {', '.join(result['changed'])}")
            if result["added"]:
                print(f"  ➕ 新增: {', '.join(result['added'])}")
            if result["deleted"]:
                print(f"  ❌ 删除: {', '.join(result['deleted'])}")

        # 对 JSON 文件做语法校验
        openclaw_path = config_root / "openclaw.json"
        if openclaw_path.exists():
            validation = validate_openclaw_config(str(openclaw_path))
            if not validation["valid"]:
                print(f"\n⛔ openclaw.json 校验失败:")
                for error_msg in validation["errors"]:
                    print(f"  - {error_msg}")
                result["openclaw_validation"] = validation

        cron_path = config_root / "cron" / "jobs.json"
        if cron_path.exists():
            json_check = validate_json_file(str(cron_path))
            if not json_check["valid"]:
                print(f"\n⛔ cron/jobs.json 语法错误: {json_check['error']}")
                result["cron_validation"] = json_check

        return result

    elif action == "rollback":
        if not target:
            print("❌ 回滚需要指定 --target 参数（如 openclaw.json）", file=sys.stderr)
            return {"error": "缺少 --target 参数"}
        result = rollback_file(config_dir, target, backup_dir, dry_run)
        prefix = "[DRY-RUN] " if dry_run else ""
        if result["status"] == "rolled_back":
            print(f"✅ {prefix}{result['detail']}")
        else:
            print(f"❌ {result['detail']}", file=sys.stderr)
        return result

    elif action == "validate":
        watched = resolve_watched_files(config_dir)
        all_valid = True
        for watched_file in watched:
            if watched_file.suffix == ".json":
                check = validate_json_file(str(watched_file))
                relative = watched_file.relative_to(config_root)
                status_icon = "✅" if check["valid"] else "⛔"
                print(f"  {status_icon} {relative}" + ("" if check["valid"] else f" — {check['error']}"))
                if not check["valid"]:
                    all_valid = False
        return {"valid": all_valid}

    else:
        return {"error": f"未知动作: {action}"}


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def build_cli_parser():
    """
    构建命令行参数解析器。

    Returns:
        argparse.ArgumentParser: 配置好的参数解析器。
    """
    parser = argparse.ArgumentParser(
        description="Config Watchdog — 配置文件安全看门狗（快照/校验/回滚）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --config-dir ~/.openclaw/ --snapshot          # 创建快照
  %(prog)s --config-dir ~/.openclaw/ --verify            # 比对变更
  %(prog)s --config-dir ~/.openclaw/ --validate          # 语法校验
  %(prog)s --config-dir ~/.openclaw/ --rollback --target openclaw.json  # 回滚
        """,
    )
    parser.add_argument("--config-dir", required=True, help="配置根目录")
    parser.add_argument("--snapshot", action="store_true", help="创建配置快照")
    parser.add_argument("--verify", action="store_true", help="与最新快照比对变更")
    parser.add_argument("--validate", action="store_true", help="校验所有 JSON 配置语法")
    parser.add_argument("--rollback", action="store_true", help="从最新快照回滚指定文件")
    parser.add_argument("--target", default=None, help="回滚目标文件的相对路径")
    parser.add_argument("--backup-dir", default=None, help="快照存储目录")
    parser.add_argument("--dry-run", action="store_true", help="仅报告不修改")
    parser.add_argument("--task-id", default=None, help="任务 ID（cron 集成）")
    return parser


def main():
    """CLI 主入口。"""
    configure_process_utf8_stdio()
    parser = build_cli_parser()
    args = parser.parse_args()

    if args.snapshot:
        action = "snapshot"
    elif args.verify:
        action = "verify"
    elif args.validate:
        action = "validate"
    elif args.rollback:
        action = "rollback"
    else:
        parser.print_help()
        sys.exit(0)

    result = run_watchdog(
        config_dir=args.config_dir,
        action=action,
        target=args.target,
        backup_dir=args.backup_dir,
        dry_run=args.dry_run,
        task_id=args.task_id,
    )

    if result.get("error"):
        sys.exit(1)

    # 有变更或校验失败则返回非零退出码
    if result.get("status") == "changes_detected":
        sys.exit(2)
    if result.get("valid") is False:
        sys.exit(3)


if __name__ == "__main__":
    main()

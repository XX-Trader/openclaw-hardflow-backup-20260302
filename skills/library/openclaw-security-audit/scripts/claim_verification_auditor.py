#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
claim_verification_auditor.py — Agent 声明交叉验证审计器

扫描 Agent 会话记录中的事实声明（如"已创建文件""已派发任务""进度XX%"等），
并对这些声明进行独立交叉验证，识别不一致项并生成审计报告。

用法:
    python claim_verification_auditor.py --help
    python claim_verification_auditor.py --session-log-dir ~/.openclaw/ops/workflow-logs/ --output-dir ~/.openclaw/ops/claim-audit/
    python claim_verification_auditor.py --session-log-dir ./test-logs/ --dry-run
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


def configure_process_utf8_stdio():
    """确保 stdout/stderr 使用 UTF-8 编码，避免中文乱码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ──────────────────────────────────────────────
# 声明提取正则模式
# ──────────────────────────────────────────────

CLAIM_PATTERNS = {
    "file_operation": {
        "patterns": [
            re.compile(r"已(?:创建|修改|写入|生成|更新)(?:了)?(?:文件)?[:\s]*[`\"']?([^\s`\"'，。]+)[`\"']?", re.UNICODE),
            re.compile(r"(?:created|modified|wrote|generated)\s+(?:file\s+)?[`\"']?([^\s`\"'，。]+)[`\"']?", re.IGNORECASE),
        ],
        "verify_fn": "verify_file_exists",
    },
    "task_dispatch": {
        "patterns": [
            re.compile(r"已(?:派发|分配|交给|发送)(?:了)?(?:任务)?(?:给)?[:\s]*[`\"']?(\w[\w-]*)[`\"']?", re.UNICODE),
            re.compile(r"已(?:派发|创建)(?:了)?(?:\d+个)?子?\s*(?:Agent|会话|session)", re.UNICODE),
            re.compile(r"dispatched?\s+(?:task\s+)?(?:to\s+)?[`\"']?(\w[\w-]*)[`\"']?", re.IGNORECASE),
        ],
        "verify_fn": "verify_task_dispatch",
    },
    "progress_report": {
        "patterns": [
            re.compile(r"进度[:\s]*(\d{1,3})\s*%", re.UNICODE),
            re.compile(r"完成度[:\s]*(\d{1,3})\s*%", re.UNICODE),
            re.compile(r"(\d{1,3})%\s*(?:完成|完)", re.UNICODE),
            re.compile(r"progress[:\s]*(\d{1,3})\s*%", re.IGNORECASE),
        ],
        "verify_fn": "verify_progress",
    },
    "session_creation": {
        "patterns": [
            re.compile(r"已(?:创建|启动|初始化)(?:了)?(?:\d+个)?(?:子)?(?:Agent|会话|session)", re.UNICODE),
            re.compile(r"session[_-]?key[:\s]*[`\"']?([a-zA-Z0-9_-]+)[`\"']?", re.IGNORECASE),
        ],
        "verify_fn": "verify_session",
    },
    "resource_consumption": {
        "patterns": [
            re.compile(r"(?:Token|token)\s*(?:消耗|使用|花费)[:\s]*[~≈约]*\s*([\d.]+)\s*(?:万|M|k)", re.UNICODE),
            re.compile(r"(?:消耗|使用)\s*(?:了)?[~≈约]*\s*([\d.]+)\s*(?:万|M)\s*(?:Token|token)", re.UNICODE),
            re.compile(r"(?:耗时|用时)[:\s]*[~≈约]*\s*([\d.]+)\s*(?:小时|分钟|秒|h|min|s)", re.UNICODE),
        ],
        "verify_fn": "verify_resource_consumption",
    },
}


def extract_claims_from_text(text, source_file="unknown"):
    """
    从文本中提取所有匹配到的事实声明。

    Args:
        text: 要扫描的文本内容。
        source_file: 来源文件路径，用于审计记录。

    Returns:
        list[dict]: 提取到的声明列表，每项包含 claim_type / matched_text / captured_group / source_file。
    """
    claims = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for claim_type, config in CLAIM_PATTERNS.items():
            for pattern in config["patterns"]:
                for match in pattern.finditer(line):
                    claim = {
                        "claim_type": claim_type,
                        "matched_text": match.group(0).strip(),
                        "captured_group": match.group(1) if match.lastindex and match.lastindex >= 1 else None,
                        "source_file": str(source_file),
                        "line_number": line_number,
                        "line_content": line.strip()[:200],
                    }
                    claims.append(claim)
    return claims


# ──────────────────────────────────────────────
# 验证函数
# ──────────────────────────────────────────────

def verify_file_exists(claim, workspace_root=None, **_kwargs):
    """
    验证声称创建/修改的文件是否实际存在。

    Args:
        claim: 声明字典，需包含 captured_group（文件路径）。
        workspace_root: 工作区根目录，用于相对路径解析。

    Returns:
        dict: 验证结果，包含 status / detail / evidence。
    """
    file_path = claim.get("captured_group")
    if not file_path:
        return {"status": "unverifiable", "detail": "无法提取文件路径", "evidence": None}

    candidates = [file_path]
    if workspace_root:
        candidates.append(os.path.join(workspace_root, file_path))

    for candidate in candidates:
        candidate_path = Path(candidate)
        if candidate_path.exists():
            stat_info = candidate_path.stat()
            return {
                "status": "verified",
                "detail": f"文件存在: {candidate}",
                "evidence": {
                    "path": str(candidate_path.resolve()),
                    "size_bytes": stat_info.st_size,
                    "mtime": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                },
            }

    return {
        "status": "inconsistent",
        "detail": f"声称操作的文件不存在: {file_path}",
        "evidence": {"checked_paths": candidates},
    }


def verify_task_dispatch(claim, task_db_path=None, **_kwargs):
    """
    验证声称的任务派发是否在 task_center.db 中有记录。

    Args:
        claim: 声明字典。
        task_db_path: task_center.db 的路径。

    Returns:
        dict: 验证结果。
    """
    if not task_db_path or not Path(task_db_path).exists():
        return {"status": "unverifiable", "detail": "task_center.db 不可用，无法验证任务派发", "evidence": None}

    target_agent = claim.get("captured_group")
    if not target_agent:
        return {"status": "unverifiable", "detail": "无法提取目标 Agent 名称", "evidence": None}

    try:
        import sqlite3
        connection = sqlite3.connect(task_db_path)
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE assignee = ? AND created_at > datetime('now', '-1 day')",
            (target_agent,),
        )
        count = cursor.fetchone()[0]
        connection.close()

        if count > 0:
            return {"status": "verified", "detail": f"最近24h内有 {count} 条派发给 {target_agent} 的任务记录", "evidence": {"task_count": count, "target_agent": target_agent}}
        else:
            return {"status": "inconsistent", "detail": f"task_center.db 中最近24h内无派发给 {target_agent} 的记录", "evidence": {"task_count": 0, "target_agent": target_agent}}
    except Exception as error:
        return {"status": "unverifiable", "detail": f"查询 task_center.db 失败: {error}", "evidence": None}


def verify_progress(claim, **_kwargs):
    """
    标记进度声明为需要进一步验证。
    进度百分比无法自动验证，但标记出来便于人工审查。

    Args:
        claim: 声明字典。

    Returns:
        dict: 验证结果（总是 unverifiable，标记为人工审查项）。
    """
    percentage = claim.get("captured_group")
    return {
        "status": "needs_human_review",
        "detail": f"声称进度 {percentage}%，需人工核实是否有对应的实际产出",
        "evidence": {"claimed_percentage": percentage},
    }


def verify_session(claim, session_dir=None, **_kwargs):
    """
    验证声称的子 Agent 会话是否实际存在。

    Args:
        claim: 声明字典。
        session_dir: 会话文件存储目录。

    Returns:
        dict: 验证结果。
    """
    session_key = claim.get("captured_group")
    if not session_key:
        return {"status": "unverifiable", "detail": "无法提取 session_key", "evidence": None}

    if session_dir:
        session_path = Path(session_dir)
        if session_path.exists():
            matching_files = list(session_path.glob(f"*{session_key}*"))
            if matching_files:
                return {"status": "verified", "detail": f"找到匹配的会话文件: {matching_files[0].name}", "evidence": {"session_files": [str(matched_file) for matched_file in matching_files[:5]]}}
            else:
                return {"status": "inconsistent", "detail": f"未找到 session_key={session_key} 的会话文件", "evidence": {"searched_dir": str(session_dir)}}

    return {"status": "unverifiable", "detail": "会话目录不可用，无法验证", "evidence": None}


def verify_resource_consumption(claim, **_kwargs):
    """
    标记资源消耗声明为需要进一步验证。

    Args:
        claim: 声明字典。

    Returns:
        dict: 验证结果（需人工审查）。
    """
    amount = claim.get("captured_group")
    return {
        "status": "needs_human_review",
        "detail": f"声称资源消耗 {amount}，需与 API 计费日志交叉验证",
        "evidence": {"claimed_amount": amount},
    }


# ──────────────────────────────────────────────
# 审计器核心
# ──────────────────────────────────────────────

VERIFY_FUNCTIONS = {
    "verify_file_exists": verify_file_exists,
    "verify_task_dispatch": verify_task_dispatch,
    "verify_progress": verify_progress,
    "verify_session": verify_session,
    "verify_resource_consumption": verify_resource_consumption,
}


def run_audit(session_log_dir, output_dir, scan_since_hours=24, task_db_path=None,
              workspace_root=None, session_dir=None, dry_run=False, task_id=None):
    """
    执行声明交叉审计的主流程。

    Args:
        session_log_dir: 会话日志目录路径。
        output_dir: 审计报告输出目录。
        scan_since_hours: 扫描最近 N 小时内的日志。
        task_db_path: task_center.db 路径（可选）。
        workspace_root: 工作区根目录（可选）。
        session_dir: 会话文件目录（可选）。
        dry_run: 仅输出报告不写文件。
        task_id: 当前任务 ID（可选，用于 cron 集成）。

    Returns:
        dict: 审计结果摘要。
    """
    log_dir = Path(session_log_dir)
    if not log_dir.exists():
        print(f"❌ 会话日志目录不存在: {session_log_dir}", file=sys.stderr)
        return {"error": f"日志目录不存在: {session_log_dir}"}

    cutoff_time = datetime.now() - timedelta(hours=scan_since_hours)

    # 收集日志文件
    log_files = []
    for extension in ("*.log", "*.jsonl", "*.txt", "*.md"):
        for log_file in log_dir.rglob(extension):
            try:
                file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_mtime >= cutoff_time:
                    log_files.append(log_file)
            except OSError:
                continue

    if not log_files:
        print(f"ℹ️ 最近 {scan_since_hours} 小时内无日志文件")
        return {"sessions_scanned": 0, "claims_found": 0}

    # 提取所有声明
    all_claims = []
    for log_file in log_files:
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
            claims = extract_claims_from_text(content, source_file=str(log_file))
            all_claims.extend(claims)
        except Exception as read_error:
            print(f"⚠️ 读取日志失败 {log_file}: {read_error}", file=sys.stderr)

    # 去重（基于 matched_text 的 hash）
    seen_hashes = set()
    unique_claims = []
    for claim in all_claims:
        claim_hash = hashlib.md5(f"{claim['claim_type']}:{claim['matched_text']}".encode()).hexdigest()[:12]
        if claim_hash not in seen_hashes:
            seen_hashes.add(claim_hash)
            claim["claim_hash"] = claim_hash
            unique_claims.append(claim)

    # 验证每条声明
    verify_context = {
        "workspace_root": workspace_root,
        "task_db_path": task_db_path,
        "session_dir": session_dir,
    }

    results = {
        "verified": [],
        "inconsistent": [],
        "unverifiable": [],
        "needs_human_review": [],
    }

    for claim in unique_claims:
        claim_config = CLAIM_PATTERNS.get(claim["claim_type"], {})
        verify_fn_name = claim_config.get("verify_fn")
        verify_fn = VERIFY_FUNCTIONS.get(verify_fn_name)

        if verify_fn:
            verification = verify_fn(claim, **verify_context)
        else:
            verification = {"status": "unverifiable", "detail": "无验证函数", "evidence": None}

        claim["verification"] = verification
        status = verification["status"]
        results.get(status, results["unverifiable"]).append(claim)

    # 生成报告
    report = build_audit_report(results, log_files, unique_claims, task_id)

    if not dry_run and output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_report_path = output_path / f"claim-audit-{timestamp}.json"
        md_report_path = output_path / f"claim-audit-{timestamp}.md"

        json_report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        md_report_path.write_text(report["markdown_report"], encoding="utf-8")

        print(f"✅ 审计报告已写入:")
        print(f"   JSON: {json_report_path}")
        print(f"   Markdown: {md_report_path}")
    else:
        print(report["markdown_report"])

    return report["summary"]


def build_audit_report(results, log_files, all_claims, task_id=None):
    """
    构建审计报告（JSON + Markdown 双格式）。

    Args:
        results: 按验证状态分类的声明字典。
        log_files: 扫描的日志文件列表。
        all_claims: 所有提取到的声明。
        task_id: 当前任务 ID（可选）。

    Returns:
        dict: 包含 summary / details / markdown_report 的完整报告。
    """
    total_claims = len(all_claims)
    verified_count = len(results["verified"])
    inconsistent_count = len(results["inconsistent"])
    unverifiable_count = len(results["unverifiable"])
    human_review_count = len(results["needs_human_review"])

    consistency_rate = (verified_count / total_claims * 100) if total_claims > 0 else 100.0

    summary = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "sessions_scanned": len(log_files),
        "claims_found": total_claims,
        "verified": verified_count,
        "inconsistent": inconsistent_count,
        "unverifiable": unverifiable_count,
        "needs_human_review": human_review_count,
        "consistency_rate_percent": round(consistency_rate, 1),
        "alert_level": "critical" if inconsistent_count >= 3 else ("warning" if inconsistent_count >= 1 else "ok"),
    }

    # Markdown 报告
    lines = [
        f"# 🔍 Agent 诚信审计报告",
        f"",
        f"> 📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"## 概览",
        f"",
        f"| 指标 | 数值 |",
        f"|---|---|",
        f"| 扫描会话数 | {len(log_files)} |",
        f"| 提取声明数 | {total_claims} |",
        f"| ✅ 已验证 | {verified_count} ({verified_count / total_claims * 100:.0f}%) |" if total_claims > 0 else f"| ✅ 已验证 | 0 |",
        f"| ⚠️ 不一致 | {inconsistent_count} ({inconsistent_count / total_claims * 100:.0f}%) |" if total_claims > 0 else f"| ⚠️ 不一致 | 0 |",
        f"| ❓ 无法验证 | {unverifiable_count} |",
        f"| 👁️ 需人工审查 | {human_review_count} |",
        f"| 诚信度 | {consistency_rate:.1f}% |",
        f"",
    ]

    if results["inconsistent"]:
        lines.append("## ⛔ 不一致声明（需关注）")
        lines.append("")
        for idx, claim in enumerate(results["inconsistent"], start=1):
            lines.append(f"### {idx}. {claim['claim_type']}")
            lines.append(f"- **声明**: `{claim['matched_text']}`")
            lines.append(f"- **来源**: `{claim['source_file']}` (L{claim['line_number']})")
            lines.append(f"- **验证结果**: {claim['verification']['detail']}")
            lines.append("")

    if results["needs_human_review"]:
        lines.append("## 👁️ 需人工审查")
        lines.append("")
        for claim in results["needs_human_review"]:
            lines.append(f"- `{claim['matched_text']}` — {claim['verification']['detail']}")
        lines.append("")

    markdown_report = "\n".join(lines)

    return {
        "summary": summary,
        "details": {
            "verified": [_claim_to_serializable(claim) for claim in results["verified"]],
            "inconsistent": [_claim_to_serializable(claim) for claim in results["inconsistent"]],
            "unverifiable": [_claim_to_serializable(claim) for claim in results["unverifiable"]],
            "needs_human_review": [_claim_to_serializable(claim) for claim in results["needs_human_review"]],
        },
        "markdown_report": markdown_report,
    }


def _claim_to_serializable(claim):
    """将声明字典转为 JSON 可序列化格式。"""
    serializable = dict(claim)
    return serializable


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
        description="Agent 声明交叉验证审计器 — 扫描 Agent 会话日志中的事实声明并验证真实性",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --session-log-dir ~/.openclaw/ops/workflow-logs/ --output-dir ~/.openclaw/ops/claim-audit/
  %(prog)s --session-log-dir ./logs/ --dry-run
  %(prog)s --session-log-dir ./logs/ --scan-since-hours 48 --task-db ~/.openclaw/ops/task_center.db
        """,
    )
    parser.add_argument("--session-log-dir", required=True, help="Agent 会话日志目录")
    parser.add_argument("--output-dir", default=None, help="审计报告输出目录")
    parser.add_argument("--scan-since-hours", type=int, default=24, help="扫描最近 N 小时的日志（默认 24）")
    parser.add_argument("--task-db", default=None, help="task_center.db 路径（用于验证任务派发）")
    parser.add_argument("--workspace-root", default=None, help="工作区根目录（用于验证文件路径）")
    parser.add_argument("--session-dir", default=None, help="Agent 会话文件目录（用于验证 session）")
    parser.add_argument("--dry-run", action="store_true", help="只输出报告到 stdout，不写文件")
    parser.add_argument("--task-id", default=None, help="当前任务 ID（用于 cron 集成）")
    return parser


def main():
    """CLI 主入口。"""
    configure_process_utf8_stdio()
    parser = build_cli_parser()
    args = parser.parse_args()

    result = run_audit(
        session_log_dir=args.session_log_dir,
        output_dir=args.output_dir,
        scan_since_hours=args.scan_since_hours,
        task_db_path=args.task_db,
        workspace_root=args.workspace_root,
        session_dir=args.session_dir,
        dry_run=args.dry_run,
        task_id=args.task_id,
    )

    if result.get("error"):
        sys.exit(1)

    # 如果有不一致声明，返回退出码 2（便于 cron 检测告警）
    if result.get("inconsistent", 0) > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()

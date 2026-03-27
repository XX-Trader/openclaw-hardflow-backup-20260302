#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
workflow_audit.py — 工作流会话审计工具

对 Agent 工作流会话进行事后审计，支持两种模式：
- summary（结果模式）: 输出简洁摘要（完成率、异常数、诚信度）
- detail（明细模式）: 逐条列出声明验证结果

用法:
    python workflow_audit.py --session-dir /path/to/session/ --mode summary
    python workflow_audit.py --session-dir /path/to/sessions/ --mode detail --batch --since-hours 24
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path


def configure_process_utf8_stdio():
    """确保 stdout/stderr 使用 UTF-8 编码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ──────────────────────────────────────────────
# 会话解析
# ──────────────────────────────────────────────

TASK_STATUS_PATTERNS = {
    "completed": re.compile(r"(?:✅|完成|已完成|DONE|completed|succeeded)", re.IGNORECASE),
    "failed": re.compile(r"(?:❌|失败|FAILED|error|异常)", re.IGNORECASE),
    "in_progress": re.compile(r"(?:⏳|进行中|IN_PROGRESS|running|执行中)", re.IGNORECASE),
    "skipped": re.compile(r"(?:⏭|跳过|SKIPPED|skip)", re.IGNORECASE),
}

CLAIM_PATTERNS = {
    "file_created": re.compile(r"(?:已创建|创建了|写入了|generated|created)\s*(?:文件|file)?\s*[`'\"]?([^\s`'\"]+)[`'\"]?", re.IGNORECASE),
    "test_passed": re.compile(r"(\d+)\s*/\s*(\d+)\s*(?:测试|tests?)\s*(?:通过|passed)", re.IGNORECASE),
    "progress_pct": re.compile(r"(?:进度|完成度|progress)\s*[:：]?\s*(\d{1,3})\s*%", re.IGNORECASE),
    "deployed": re.compile(r"(?:已部署|deployed|上线|发布)\s*(?:到|to)?\s*([^\s,。！]+)", re.IGNORECASE),
}


def parse_session_logs(session_dir):
    """
    解析会话目录中的所有日志文件。

    Args:
        session_dir: 会话目录路径。

    Returns:
        dict: 解析结果（tasks / claims / errors / metadata）。
    """
    session_path = Path(session_dir)
    if not session_path.exists():
        return {"error": f"会话目录不存在: {session_dir}"}

    log_files = list(session_path.rglob("*.log")) + list(session_path.rglob("*.jsonl")) + list(session_path.rglob("*.md"))

    tasks = []
    claims = []
    errors = []
    total_lines = 0

    for log_file in log_files:
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            total_lines += 1

            # 检测任务状态声明
            for status_name, status_pattern in TASK_STATUS_PATTERNS.items():
                if status_pattern.search(line):
                    tasks.append({
                        "status": status_name,
                        "line": line.strip()[:200],
                        "source": str(log_file.name),
                        "line_number": line_number,
                    })
                    break

            # 检测事实声明
            for claim_type, claim_pattern in CLAIM_PATTERNS.items():
                match = claim_pattern.search(line)
                if match:
                    claims.append({
                        "type": claim_type,
                        "match": match.group(0)[:200],
                        "groups": list(match.groups()),
                        "source": str(log_file.name),
                        "line_number": line_number,
                    })

            # 检测错误行
            if re.search(r"(?:ERROR|CRITICAL|FATAL|❌|失败)", line, re.IGNORECASE):
                errors.append({
                    "line": line.strip()[:200],
                    "source": str(log_file.name),
                    "line_number": line_number,
                })

    return {
        "session_dir": str(session_dir),
        "log_files_count": len(log_files),
        "total_lines": total_lines,
        "tasks": tasks,
        "claims": claims,
        "errors": errors,
    }


# ──────────────────────────────────────────────
# 审计评分
# ──────────────────────────────────────────────

def compute_audit_score(parsed):
    """
    基于解析结果计算审计评分。

    Args:
        parsed: parse_session_logs 的返回值。

    Returns:
        dict: 审计评分（completion_rate / claim_density / error_rate / integrity_score）。
    """
    tasks = parsed.get("tasks", [])
    claims = parsed.get("claims", [])
    errors = parsed.get("errors", [])
    total_lines = parsed.get("total_lines", 0)

    # 完成率
    completed_count = sum(1 for t in tasks if t["status"] == "completed")
    failed_count = sum(1 for t in tasks if t["status"] == "failed")
    total_tasks = completed_count + failed_count
    completion_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0

    # 声明密度（每百行日志中的声明数）
    claim_density = (len(claims) / max(total_lines, 1)) * 100

    # 错误率
    error_rate = (len(errors) / max(total_lines, 1)) * 100

    # 诚信度评分（基于声明合理性）
    # 高密度声明 + 低错误 = 可疑（可能在编造）
    # 合理密度 + 对应错误 = 健康
    if claim_density > 10 and error_rate < 0.5:
        integrity_score = max(50 - (claim_density - 10) * 2, 20)  # 声明过密且无错误→可疑
    elif total_tasks == 0 and len(claims) == 0:
        integrity_score = 50  # 无数据
    else:
        integrity_score = min(100, 70 + completion_rate * 0.3 - error_rate * 5)

    return {
        "completion_rate": round(completion_rate, 1),
        "completed": completed_count,
        "failed": failed_count,
        "total_tasks": total_tasks,
        "claim_count": len(claims),
        "claim_density": round(claim_density, 2),
        "error_count": len(errors),
        "error_rate": round(error_rate, 2),
        "integrity_score": round(max(0, min(100, integrity_score)), 1),
    }


# ──────────────────────────────────────────────
# 报告生成
# ──────────────────────────────────────────────

def build_summary_report(parsed, score):
    """构建结果模式摘要报告。"""
    lines = [
        "# 📋 工作流审计摘要",
        "",
        f"> 📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 会话: `{parsed.get('session_dir', 'N/A')}`",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 日志文件 | {parsed.get('log_files_count', 0)} |",
        f"| 总行数 | {parsed.get('total_lines', 0)} |",
        f"| 任务完成率 | {score['completion_rate']}%（{score['completed']}/{score['total_tasks']}） |",
        f"| 声明数 | {score['claim_count']}（密度: {score['claim_density']}%） |",
        f"| 错误数 | {score['error_count']} |",
        f"| **诚信度评分** | **{score['integrity_score']}** |",
        "",
    ]

    if score["integrity_score"] < 50:
        lines.append("> [!WARNING]")
        lines.append(f"> 诚信度评分偏低（{score['integrity_score']}），建议人工复审此会话")
        lines.append("")

    return "\n".join(lines)


def build_detail_report(parsed, score):
    """构建明细模式报告。"""
    lines = [build_summary_report(parsed, score)]

    claims = parsed.get("claims", [])
    if claims:
        lines.append("## 事实声明明细")
        lines.append("")
        lines.append("| # | 类型 | 内容 | 来源 |")
        lines.append("|---|---|---|---|")
        for idx, claim in enumerate(claims[:50], start=1):
            lines.append(f"| {idx} | {claim['type']} | `{claim['match'][:80]}` | {claim['source']}:L{claim['line_number']} |")
        lines.append("")

    errors = parsed.get("errors", [])
    if errors:
        lines.append("## 错误记录")
        lines.append("")
        for err in errors[:20]:
            lines.append(f"- `{err['line'][:100]}` ({err['source']}:L{err['line_number']})")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def run_audit(session_dir, mode="summary", output_dir=None, batch=False,
              since_hours=24, dry_run=False, task_id=None):
    """
    执行工作流审计的主流程。

    Args:
        session_dir: 会话目录。
        mode: 审计模式（"summary" / "detail"）。
        output_dir: 报告输出目录。
        batch: 批量扫描子目录。
        since_hours: 扫描最近 N 小时。
        dry_run: 仅输出不写文件。
        task_id: 任务 ID。

    Returns:
        dict: 审计结果。
    """
    session_path = Path(session_dir)
    cutoff = datetime.now() - timedelta(hours=since_hours)

    sessions_to_audit = []
    if batch:
        for sub_dir in session_path.iterdir():
            if sub_dir.is_dir():
                try:
                    mtime = datetime.fromtimestamp(sub_dir.stat().st_mtime)
                    if mtime >= cutoff:
                        sessions_to_audit.append(sub_dir)
                except OSError:
                    continue
    else:
        sessions_to_audit = [session_path]

    all_results = []
    for session in sessions_to_audit:
        parsed = parse_session_logs(session)
        if "error" in parsed:
            print(f"⚠️ {parsed['error']}", file=sys.stderr)
            continue

        score = compute_audit_score(parsed)

        if mode == "detail":
            report = build_detail_report(parsed, score)
        else:
            report = build_summary_report(parsed, score)

        all_results.append({
            "session": str(session),
            "score": score,
            "report": report,
        })

        if not dry_run and output_dir:
            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_name = session.name[:20]

            json_path = out_path / f"audit-{session_name}-{timestamp}.json"
            json_path.write_text(json.dumps({
                "score": score,
                "claims": parsed.get("claims", [])[:100],
                "errors": parsed.get("errors", [])[:50],
            }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

            md_path = out_path / f"audit-{session_name}-{timestamp}.md"
            md_path.write_text(report, encoding="utf-8")
        else:
            print(report)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "sessions_audited": len(all_results),
        "avg_integrity": round(
            sum(r["score"]["integrity_score"] for r in all_results) / max(len(all_results), 1), 1
        ),
        "sessions_needing_review": [
            r["session"] for r in all_results if r["score"]["integrity_score"] < 50
        ],
    }

    return summary


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def build_cli_parser():
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="工作流会话审计 — 结果模式/明细模式两种输出",
    )
    parser.add_argument("--session-dir", required=True, help="会话目录")
    parser.add_argument("--mode", choices=["summary", "detail"], default="summary", help="审计模式")
    parser.add_argument("--output-dir", default=None, help="报告输出目录")
    parser.add_argument("--batch", action="store_true", help="批量扫描子目录")
    parser.add_argument("--since-hours", type=int, default=24, help="扫描最近 N 小时")
    parser.add_argument("--dry-run", action="store_true", help="只输出不写文件")
    parser.add_argument("--task-id", default=None, help="任务 ID")
    return parser


def main():
    """CLI 主入口。"""
    configure_process_utf8_stdio()
    parser = build_cli_parser()
    args = parser.parse_args()

    result = run_audit(
        session_dir=args.session_dir,
        mode=args.mode,
        output_dir=args.output_dir,
        batch=args.batch,
        since_hours=args.since_hours,
        dry_run=args.dry_run,
        task_id=args.task_id,
    )

    review_count = len(result.get("sessions_needing_review", []))
    if review_count > 0:
        sys.exit(2)


if __name__ == "__main__":
    main()

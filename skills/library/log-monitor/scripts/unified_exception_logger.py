#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
unified_exception_logger.py — 统一异常日志收集与分类巡检

扫描 Agent 工作流日志中的异常/错误/警告记录，按类型自动分类、去重、
统计频率，并生成结构化巡检报告。

分类维度：
- API 错误（模型调用失败、限速、超时）
- 文件系统错误（权限、路径不存在、磁盘满）
- 配置错误（JSON 语法、引用缺失）
- Agent 通信错误（子会话创建失败、消息投递失败）
- 系统错误（OOM、进程崩溃）

用法:
    python unified_exception_logger.py --help
    python unified_exception_logger.py --auto-discover --dry-run
    python unified_exception_logger.py --auto-discover --output-dir ~/.openclaw/ops/exception-reports/
    python unified_exception_logger.py --log-dirs ~/.openclaw/ops/workflow-logs/ --dry-run
    python unified_exception_logger.py --log-dirs /dir1 /dir2 --output-dir ~/.openclaw/ops/exception-reports/
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def configure_process_utf8_stdio():
    """确保 stdout/stderr 使用 UTF-8 编码，避免中文乱码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# ──────────────────────────────────────────────
# Auto-discover: 自动发现 ~/.openclaw/ 下的日志目录
# ──────────────────────────────────────────────

AUTO_DISCOVER_PATTERNS: list[str] = [
    "agents/*/sessions",
    "ops/task-center/executor-runs",
    "ops/exception-reports",
    "ops/workflow-logs",
    "logs",
    "workspace-*/sessions",
    "subagents/*/sessions",
]


def discover_log_dirs(openclaw_home: str) -> list[str]:
    """自动发现 openclaw_home 下所有存在的日志目录。

    Args:
        openclaw_home: OpenClaw 根目录路径（如 ~/.openclaw）。

    Returns:
        list[str]: 已存在的日志目录绝对路径列表。
    """
    home = Path(openclaw_home).expanduser().resolve()
    if not home.is_dir():
        return []
    found: list[str] = []
    for pattern in AUTO_DISCOVER_PATTERNS:
        for match in sorted(home.glob(pattern)):
            if match.is_dir() and str(match) not in found:
                found.append(str(match))
    return found


# ──────────────────────────────────────────────
# 异常分类正则
# ──────────────────────────────────────────────

EXCEPTION_CATEGORIES = {
    "api_error": {
        "label": "API 错误",
        "patterns": [
            re.compile(r"(?:rate.?limit|429|too many requests)", re.IGNORECASE),
            re.compile(r"(?:api|model)\s*(?:error|failure|timeout|refused)", re.IGNORECASE),
            re.compile(r"(?:openai|anthropic|openrouter)\s*(?:error|exception)", re.IGNORECASE),
            re.compile(r"(?:context.?length|token.?limit)\s*(?:exceeded|overflow)", re.IGNORECASE),
            re.compile(r"(?:500|502|503|504)\s*(?:error|internal|gateway|timeout)", re.IGNORECASE),
        ],
    },
    "filesystem_error": {
        "label": "文件系统错误",
        "patterns": [
            re.compile(r"(?:permission|access)\s*(?:denied|error)", re.IGNORECASE),
            re.compile(r"(?:no such file|file not found|ENOENT|FileNotFoundError)", re.IGNORECASE),
            re.compile(r"(?:disk\s*full|no space|ENOSPC)", re.IGNORECASE),
            re.compile(r"(?:read.?only|EROFS)", re.IGNORECASE),
        ],
    },
    "config_error": {
        "label": "配置错误",
        "patterns": [
            re.compile(r"(?:json|yaml|toml)\s*(?:parse|syntax)\s*error", re.IGNORECASE),
            re.compile(r"(?:invalid|malformed|missing)\s*(?:config|configuration|setting)", re.IGNORECASE),
            re.compile(r"(?:plugin|skill|hook)\s*.{0,60}(?:not found|missing|unavailable)", re.IGNORECASE),
            re.compile(r"SyntaxError.*JSON", re.IGNORECASE),
        ],
    },
    "agent_comm_error": {
        "label": "Agent 通信错误",
        "patterns": [
            re.compile(r"(?:session|sub.?agent)\s*(?:creation|dispatch|spawn)\s*(?:failed|error)", re.IGNORECASE),
            re.compile(r"(?:message|delivery|notification)\s*(?:failed|error|timeout)", re.IGNORECASE),
            re.compile(r"(?:agent.?to.?agent|a2a)\s*(?:error|failed|refused)", re.IGNORECASE),
            re.compile(r"子(?:Agent|会话)\s*(?:创建|派发|启动)\s*(?:失败|错误|超时)", re.UNICODE),
        ],
    },
    "system_error": {
        "label": "系统错误",
        "patterns": [
            re.compile(r"(?:out of memory|OOM|MemoryError|ENOMEM)", re.IGNORECASE),
            re.compile(r"(?:segfault|segmentation fault|SIGSEGV|SIGKILL)", re.IGNORECASE),
            re.compile(r"(?:process|worker)\s*(?:crashed|killed|terminated)", re.IGNORECASE),
            re.compile(r"(?:Traceback|stack trace|panic)", re.IGNORECASE),
        ],
    },
    "path_validation_error": {
        "label": "路径校验错误",
        "patterns": [
            re.compile(r"(?:invalid|illegal|bad)\s*(?:path|directory|file\s*name)", re.IGNORECASE),
            re.compile(r"path\s*(?:traversal|injection|escape)", re.IGNORECASE),
            re.compile(r"(?:\.\.[\\/]|~[\\/]|\$\{|\$HOME)", re.IGNORECASE),
            re.compile(r"(?:symlink|hardlink)\s*(?:attack|loop|refused)", re.IGNORECASE),
            re.compile(r"路径[\s]*(?:非法|无效|越权|注入)", re.UNICODE),
        ],
    },
    "generic_error": {
        "label": "通用错误",
        "patterns": [
            re.compile(r"(?:^|\s)(?:ERROR|CRITICAL|FATAL)[\s:]+", re.IGNORECASE),
            re.compile(r"(?:Exception|Error):\s+\S+", re.IGNORECASE),
            re.compile(r"❌\s+", re.UNICODE),
            re.compile(r"失败[：:]\s*", re.UNICODE),
        ],
    },
}


def classify_exception(line):
    """
    将日志行分类到异常类别。

    Args:
        line: 日志行文本。

    Returns:
        str | None: 匹配的类别名（如 "api_error"），无匹配返回 None。
    """
    for category_name, category_config in EXCEPTION_CATEGORIES.items():
        for pattern in category_config["patterns"]:
            if pattern.search(line):
                return category_name
    return None


def extract_exceptions_from_file(file_path, scan_since=None):
    """
    从单个日志文件中提取异常记录。

    Args:
        file_path: 日志文件路径。
        scan_since: 截止时间过滤（基于文件修改时间）。

    Returns:
        list[dict]: 提取的异常记录列表。
    """
    target = Path(file_path)
    if not target.exists():
        return []

    if scan_since:
        try:
            file_mtime = datetime.fromtimestamp(target.stat().st_mtime)
            if file_mtime < scan_since:
                return []
        except OSError:
            return []

    exceptions = []
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    for line_number, line in enumerate(content.splitlines(), start=1):
        category = classify_exception(line)
        if category:
            # 生成去重 fingerprint（忽略时间戳和内存地址等变量部分）
            normalized = re.sub(r"\d{4}[-/]\d{2}[-/]\d{2}[\sT]\d{2}:\d{2}:\d{2}", "TIMESTAMP", line)
            normalized = re.sub(r"0x[0-9a-fA-F]+", "ADDR", normalized)
            normalized = re.sub(r"\d{5,}", "NUM", normalized)
            fingerprint = hashlib.md5(f"{category}:{normalized.strip()[:120]}".encode()).hexdigest()[:10]

            exceptions.append({
                "category": category,
                "category_label": EXCEPTION_CATEGORIES[category]["label"],
                "line_number": line_number,
                "line_content": line.strip()[:300],
                "source_file": str(file_path),
                "fingerprint": fingerprint,
            })

    return exceptions


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def run_exception_scan(log_dirs, output_dir=None, scan_since_hours=24,
                       dry_run=False, task_id=None,
                       abnormal_dir=None, cleanup=False):
    """
    执行统一异常扫描的主流程。

    Args:
        log_dirs: 日志目录列表。
        output_dir: 报告输出目录。
        scan_since_hours: 扫描最近 N 小时。
        dry_run: 仅输出不写文件。
        task_id: 任务 ID。

    Returns:
        dict: 扫描结果摘要。
    """
    cutoff_time = datetime.now() - timedelta(hours=scan_since_hours)

    all_exceptions = []
    scanned_files = 0

    for log_dir_str in log_dirs:
        log_dir = Path(log_dir_str)
        if not log_dir.exists():
            # 静默跳过不存在的目录（cron 环境下部分目录可能未创建）
            continue

        for extension in ("*.log", "*.jsonl", "*.txt", "*.md"):
            for log_file in log_dir.rglob(extension):
                scanned_files += 1
                file_exceptions = extract_exceptions_from_file(log_file, scan_since=cutoff_time)
                all_exceptions.extend(file_exceptions)

    # 去重（基于 fingerprint）
    seen_fingerprints = Counter()
    unique_exceptions = []
    for exc in all_exceptions:
        fp = exc["fingerprint"]
        seen_fingerprints[fp] += 1
        if seen_fingerprints[fp] == 1:
            unique_exceptions.append(exc)

    # 为每个去重后的异常附加出现次数
    for exc in unique_exceptions:
        exc["occurrence_count"] = seen_fingerprints[exc["fingerprint"]]

    # 按类别分组统计
    category_stats = defaultdict(lambda: {"count": 0, "unique": 0, "samples": []})
    for exc in unique_exceptions:
        cat = exc["category"]
        category_stats[cat]["count"] += exc["occurrence_count"]
        category_stats[cat]["unique"] += 1
        if len(category_stats[cat]["samples"]) < 3:
            category_stats[cat]["samples"].append(exc["line_content"][:150])

    # 构建报告
    summary = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "scan_since_hours": scan_since_hours,
        "scanned_files": scanned_files,
        "total_exceptions": sum(seen_fingerprints.values()),
        "unique_exceptions": len(unique_exceptions),
        "category_breakdown": {
            cat: {
                "label": EXCEPTION_CATEGORIES.get(cat, {}).get("label", cat),
                "total": stats["count"],
                "unique": stats["unique"],
            }
            for cat, stats in sorted(category_stats.items(), key=lambda x: x[1]["count"], reverse=True)
        },
        "alert_level": _compute_alert_level(category_stats),
    }

    # Markdown 报告
    markdown_report = _build_markdown_report(summary, category_stats, unique_exceptions)

    if not dry_run and output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        json_path = out_path / f"exception-report-{timestamp}.json"
        json_path.write_text(json.dumps({
            "summary": summary,
            "exceptions": [_exc_to_serializable(e) for e in unique_exceptions],
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        md_path = out_path / f"exception-report-{timestamp}.md"
        md_path.write_text(markdown_report, encoding="utf-8")

        print(f"✅ 异常报告已写入:")
        print(f"   JSON: {json_path}")
        print(f"   Markdown: {md_path}")

        # 归档到统一异常日志目录
        if abnormal_dir:
            archive_to_abnormal(
                abnormal_dir=Path(abnormal_dir),
                json_path=json_path,
                md_path=md_path,
                task_id=task_id,
            )
    else:
        print(markdown_report)

    # 自动清理旧报告
    if cleanup and output_dir:
        cleanup_old_reports(Path(output_dir))
    if cleanup and abnormal_dir:
        cleanup_old_reports(Path(abnormal_dir))

    return summary


def _compute_alert_level(category_stats):
    """根据异常分布计算告警级别。"""
    system_count = category_stats.get("system_error", {}).get("count", 0)
    config_count = category_stats.get("config_error", {}).get("count", 0)
    total = sum(s["count"] for s in category_stats.values())

    if system_count >= 3 or total >= 50:
        return "critical"
    elif config_count >= 3 or total >= 20:
        return "warning"
    elif total > 0:
        return "info"
    return "ok"


def _build_markdown_report(summary, category_stats, unique_exceptions):
    """构建 Markdown 格式异常报告。"""
    lines = [
        "# 🚨 统一异常巡检报告",
        "",
        f"> 📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 扫描范围: 最近 {summary['scan_since_hours']} 小时",
        "",
        "## 概览",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 扫描文件数 | {summary['scanned_files']} |",
        f"| 异常总数 | {summary['total_exceptions']} |",
        f"| 去重后 | {summary['unique_exceptions']} |",
        f"| 告警级别 | {summary['alert_level']} |",
        "",
    ]

    if category_stats:
        lines.append("## 分类统计")
        lines.append("")
        lines.append("| 类别 | 总数 | 去重 | 示例 |")
        lines.append("|---|---|---|---|")
        for cat, stats in sorted(category_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            label = EXCEPTION_CATEGORIES.get(cat, {}).get("label", cat)
            sample = stats["samples"][0][:60] if stats["samples"] else "-"
            lines.append(f"| {label} | {stats['count']} | {stats['unique']} | `{sample}` |")
        lines.append("")

    if summary["alert_level"] in ("critical", "warning"):
        lines.append("## ⚠️ 需要关注的异常")
        lines.append("")
        priority_categories = ["system_error", "config_error", "agent_comm_error"]
        for exc in unique_exceptions:
            if exc["category"] in priority_categories:
                lines.append(f"- **[{exc['category_label']}]** `{exc['line_content'][:100]}` (×{exc['occurrence_count']})")
        lines.append("")

    return "\n".join(lines)


def _exc_to_serializable(exc):
    """将异常记录转为 JSON 可序列化格式。"""
    return dict(exc)


def archive_to_abnormal(abnormal_dir, json_path, md_path, task_id=None):
    """将巡检报告归档到统一异常日志目录。

    Args:
        abnormal_dir: 归档目标目录（如 ~/.openclaw/logs/abnormal/）。
        json_path: JSON 报告路径。
        md_path: Markdown 报告路径。
        task_id: 任务 ID（用于归档文件名前缀）。
    """
    abnormal_dir.mkdir(parents=True, exist_ok=True)
    prefix = task_id.replace(":", "_") if task_id else "exception"
    date_str = datetime.now().strftime("%Y%m%d")
    for src in (json_path, md_path):
        if src.exists():
            dest = abnormal_dir / f"{date_str}-{prefix}-{src.name}"
            try:
                shutil.copy2(str(src), str(dest))
            except OSError as exc:
                print(f"⚠️ 归档失败: {src} → {dest}: {exc}", file=sys.stderr)
    print(f"✅ 已归档到: {abnormal_dir}")


def cleanup_old_reports(report_dir, compress_days=7, delete_days=30):
    """自动清理旧报告：7天以上压缩为 .gz，30天以上删除。

    Args:
        report_dir: 报告所在目录。
        compress_days: 超过此天数的文件压缩（默认 7 天）。
        delete_days: 超过此天数的文件删除（默认 30 天）。
    """
    if not report_dir.exists():
        return
    now_ts = datetime.now().timestamp()
    compress_cutoff = now_ts - (compress_days * 86400)
    delete_cutoff = now_ts - (delete_days * 86400)
    compressed = 0
    deleted = 0
    for fpath in report_dir.iterdir():
        if not fpath.is_file():
            continue
        try:
            mtime = fpath.stat().st_mtime
        except OSError:
            continue
        # 超过 30 天：直接删除（含 .gz）
        if mtime < delete_cutoff:
            try:
                fpath.unlink()
                deleted += 1
            except OSError:
                pass
            continue
        # 超过 7 天且未压缩：gzip 压缩
        if mtime < compress_cutoff and fpath.suffix not in (".gz",):
            gz_path = fpath.with_suffix(fpath.suffix + ".gz")
            try:
                with open(str(fpath), "rb") as f_in:
                    with gzip.open(str(gz_path), "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                # 保留原始修改时间
                os.utime(str(gz_path), (mtime, mtime))
                fpath.unlink()
                compressed += 1
            except OSError:
                pass
    if compressed or deleted:
        print(f"🧹 清理完成: 压缩 {compressed} / 删除 {deleted} 个文件 ({report_dir})")


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
        description="统一异常日志收集与分类巡检 — 扫描工作流日志中的异常并按类型分类统计",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --log-dirs ~/.openclaw/ops/workflow-logs/ --dry-run
  %(prog)s --log-dirs /dir1 /dir2 --output-dir ~/.openclaw/ops/exception-reports/
  %(prog)s --log-dirs ./logs/ --scan-since-hours 48
        """,
    )
    parser.add_argument("--log-dirs", nargs="+", default=None, help="日志目录列表（与 --auto-discover 二选一）")
    parser.add_argument("--auto-discover", action="store_true",
                        help="自动发现 ~/.openclaw/ 下的日志目录（agent sessions、executor runs 等）")
    parser.add_argument("--openclaw-home", default=os.path.expanduser("~/.openclaw"),
                        help="OpenClaw 根目录，供 --auto-discover 使用（默认 ~/.openclaw）")
    parser.add_argument("--output-dir", default=None, help="报告输出目录")
    parser.add_argument("--abnormal-dir", default=None, help="统一异常日志归档目录（如 ~/.openclaw/logs/abnormal/）")
    parser.add_argument("--scan-since-hours", type=int, default=24, help="扫描最近 N 小时（默认 24）")
    parser.add_argument("--dry-run", action="store_true", help="只输出不写文件")
    parser.add_argument("--cleanup", action="store_true", help="自动清理旧报告（7天压缩/30天删除）")
    parser.add_argument("--task-id", default=None, help="任务 ID（cron 集成）")
    return parser


def main():
    """CLI 主入口。"""
    configure_process_utf8_stdio()
    parser = build_cli_parser()
    args = parser.parse_args()

    # 确定日志目录：--auto-discover 自动发现，或 --log-dirs 手动指定
    log_dirs = args.log_dirs
    if args.auto_discover:
        discovered = discover_log_dirs(args.openclaw_home)
        if log_dirs:
            # 合并手动指定 + 自动发现，去重
            merged = list(log_dirs)
            for d in discovered:
                if d not in merged:
                    merged.append(d)
            log_dirs = merged
        else:
            log_dirs = discovered
        if not log_dirs:
            print(f"⚠️ --auto-discover 未发现任何日志目录 (openclaw_home={args.openclaw_home})", file=sys.stderr)
            return
    if not log_dirs:
        print("错误: 必须指定 --log-dirs 或 --auto-discover", file=sys.stderr)
        sys.exit(1)

    result = run_exception_scan(
        log_dirs=log_dirs,
        output_dir=args.output_dir,
        scan_since_hours=args.scan_since_hours,
        dry_run=args.dry_run,
        task_id=args.task_id,
        abnormal_dir=args.abnormal_dir,
        cleanup=args.cleanup,
    )

    if result.get("alert_level") == "critical":
        sys.exit(2)
    elif result.get("alert_level") == "warning":
        sys.exit(1)


if __name__ == "__main__":
    main()

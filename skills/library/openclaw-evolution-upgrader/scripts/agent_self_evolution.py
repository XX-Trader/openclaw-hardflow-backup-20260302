#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_self_evolution.py — Agent 自进化优化引擎

基于历史任务数据（task_center.db）对每个 Agent 进行多维度评分，
识别持续低效 Agent 并生成优化建议（提示词调优 / 模型升级 / 技能补充）。

评分维度：
- 成功率：任务完成 vs 失败比
- 效率：Token 消耗 / 耗时 vs 基准对比
- 质量：quality_score 均值
- 可靠性：连续失败次数、SLA 违反率

用法:
    python agent_self_evolution.py --help
    python agent_self_evolution.py --db-path /root/.openclaw/ops/task_center.db --dry-run
    python agent_self_evolution.py --db-path task_center.db --output-dir ./evolution-reports/
"""

import argparse
import json
import sqlite3
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
# 评分权重配置
# ──────────────────────────────────────────────

SCORING_WEIGHTS = {
    "success_rate": 0.30,
    "efficiency": 0.25,
    "quality": 0.25,
    "reliability": 0.20,
}

SCORE_THRESHOLDS = {
    "excellent": 85,
    "good": 70,
    "needs_improvement": 50,
    "critical": 0,
}


# ──────────────────────────────────────────────
# 数据采集
# ──────────────────────────────────────────────

def collect_agent_metrics(db_path, lookback_days=30):
    """
    从 task_center.db 采集每个 Agent 的历史任务指标。

    Args:
        db_path: task_center.db 路径。
        lookback_days: 回溯天数。

    Returns:
        dict[str, dict]: Agent 名称到指标字典的映射。
    """
    db_file = Path(db_path)
    if not db_file.exists():
        return {}

    cutoff_iso = (datetime.now() - timedelta(days=lookback_days)).isoformat()

    try:
        connection = sqlite3.connect(str(db_file))
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()

        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}

        agent_metrics = {}

        if "task_outputs" in existing_tables:
            cursor.execute("""
                SELECT
                    agent_id,
                    COUNT(*) as total_tasks,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    AVG(CASE WHEN quality_score IS NOT NULL THEN quality_score END) as avg_quality,
                    AVG(CASE WHEN token_count IS NOT NULL THEN token_count END) as avg_tokens,
                    AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms END) as avg_duration_ms,
                    MAX(failure_count) as max_consecutive_failures
                FROM task_outputs
                WHERE created_at >= ?
                GROUP BY agent_id
            """, (cutoff_iso,))

            for row in cursor.fetchall():
                agent_id = row["agent_id"]
                total = row["total_tasks"] or 0
                completed = row["completed"] or 0
                failed = row["failed"] or 0

                agent_metrics[agent_id] = {
                    "total_tasks": total,
                    "completed": completed,
                    "failed": failed,
                    "success_rate": (completed / total * 100) if total > 0 else 0,
                    "avg_quality": row["avg_quality"] or 0,
                    "avg_tokens": row["avg_tokens"] or 0,
                    "avg_duration_ms": row["avg_duration_ms"] or 0,
                    "max_consecutive_failures": row["max_consecutive_failures"] or 0,
                }

        if "task_incidents" in existing_tables:
            cursor.execute("""
                SELECT agent_id, COUNT(*) as incident_count
                FROM task_incidents
                WHERE created_at >= ?
                GROUP BY agent_id
            """, (cutoff_iso,))

            for row in cursor.fetchall():
                agent_id = row["agent_id"]
                if agent_id in agent_metrics:
                    agent_metrics[agent_id]["incident_count"] = row["incident_count"]

        connection.close()
        return agent_metrics

    except Exception as db_error:
        print(f"⚠️ 数据库查询失败: {db_error}", file=sys.stderr)
        return {}


# ──────────────────────────────────────────────
# 评分计算
# ──────────────────────────────────────────────

def compute_agent_scores(agent_metrics):
    """
    对每个 Agent 计算多维度综合评分。

    Args:
        agent_metrics: Agent 指标字典。

    Returns:
        dict[str, dict]: Agent 名称到评分明细的映射。
    """
    scored_agents = {}

    for agent_id, metrics in agent_metrics.items():
        # 成功率评分（0-100）
        success_score = min(metrics.get("success_rate", 0), 100)

        # 效率评分（基于 Token 效率，越少越好）
        avg_tokens = metrics.get("avg_tokens", 0)
        if avg_tokens > 0:
            # 基准：50K tokens 为 50 分，10K 为 100 分，100K+ 为 20 分
            if avg_tokens <= 10000:
                efficiency_score = 100
            elif avg_tokens <= 50000:
                efficiency_score = 100 - (avg_tokens - 10000) / 40000 * 50
            elif avg_tokens <= 100000:
                efficiency_score = 50 - (avg_tokens - 50000) / 50000 * 30
            else:
                efficiency_score = max(20 - (avg_tokens - 100000) / 100000 * 10, 0)
        else:
            efficiency_score = 50  # 无数据给中间分

        # 质量评分（直接使用 avg_quality，归一化到 0-100）
        quality_score = min(metrics.get("avg_quality", 50), 100)

        # 可靠性评分（基于连续失败和事故数）
        max_failures = metrics.get("max_consecutive_failures", 0)
        incidents = metrics.get("incident_count", 0)
        reliability_score = max(100 - max_failures * 15 - incidents * 5, 0)

        # 加权综合分
        composite = (
            success_score * SCORING_WEIGHTS["success_rate"]
            + efficiency_score * SCORING_WEIGHTS["efficiency"]
            + quality_score * SCORING_WEIGHTS["quality"]
            + reliability_score * SCORING_WEIGHTS["reliability"]
        )

        # 分级
        if composite >= SCORE_THRESHOLDS["excellent"]:
            grade = "excellent"
        elif composite >= SCORE_THRESHOLDS["good"]:
            grade = "good"
        elif composite >= SCORE_THRESHOLDS["needs_improvement"]:
            grade = "needs_improvement"
        else:
            grade = "critical"

        scored_agents[agent_id] = {
            "composite_score": round(composite, 1),
            "grade": grade,
            "dimensions": {
                "success_rate": round(success_score, 1),
                "efficiency": round(efficiency_score, 1),
                "quality": round(quality_score, 1),
                "reliability": round(reliability_score, 1),
            },
            "metrics": metrics,
            "recommendations": _generate_recommendations(agent_id, composite, success_score, efficiency_score, quality_score, reliability_score, metrics),
        }

    return scored_agents


def _generate_recommendations(agent_id, composite, success_rate, efficiency,
                              quality, reliability, metrics):
    """根据评分短板生成优化建议。"""
    recommendations = []

    if success_rate < 60:
        recommendations.append({
            "area": "成功率",
            "action": "review_prompt",
            "detail": f"成功率仅 {success_rate:.0f}%，建议审查 SOUL.md 提示词和任务分发逻辑",
        })

    if efficiency < 40:
        avg_tokens = metrics.get("avg_tokens", 0)
        recommendations.append({
            "area": "效率",
            "action": "optimize_tokens",
            "detail": f"平均 Token 消耗 {avg_tokens/1000:.1f}K，考虑切换更轻量模型或优化提示词",
        })

    if quality < 50:
        recommendations.append({
            "area": "质量",
            "action": "upgrade_model",
            "detail": f"质量评分仅 {quality:.0f}，建议升级到更高能力模型或增加验证步骤",
        })

    if reliability < 50:
        max_failures = metrics.get("max_consecutive_failures", 0)
        recommendations.append({
            "area": "可靠性",
            "action": "add_retry_logic",
            "detail": f"最高连续失败 {max_failures} 次，建议增加重试和降级逻辑",
        })

    if not recommendations:
        recommendations.append({
            "area": "整体",
            "action": "maintain",
            "detail": "各项指标正常，保持当前配置",
        })

    return recommendations


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def run_evolution(db_path, output_dir=None, lookback_days=30, dry_run=False, task_id=None):
    """
    执行 Agent 自进化评估的主流程。

    Args:
        db_path: task_center.db 路径。
        output_dir: 报告输出目录。
        lookback_days: 回溯天数。
        dry_run: 仅输出不写文件。
        task_id: 任务 ID。

    Returns:
        dict: 进化评估结果。
    """
    metrics = collect_agent_metrics(db_path, lookback_days)

    if not metrics:
        print("ℹ️ 无可用的 Agent 历史数据")
        return {"agents_evaluated": 0, "status": "no_data"}

    scores = compute_agent_scores(metrics)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "task_id": task_id,
        "lookback_days": lookback_days,
        "agents_evaluated": len(scores),
        "grade_distribution": {},
        "agents_needing_attention": [],
    }

    grade_counts = {}
    for agent_id, score_data in scores.items():
        grade = score_data["grade"]
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
        if grade in ("needs_improvement", "critical"):
            summary["agents_needing_attention"].append({
                "agent_id": agent_id,
                "score": score_data["composite_score"],
                "grade": grade,
                "top_recommendation": score_data["recommendations"][0] if score_data["recommendations"] else None,
            })

    summary["grade_distribution"] = grade_counts

    # Markdown 报告
    markdown = _build_evolution_report(summary, scores)

    if not dry_run and output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        json_path = out_path / f"evolution-{timestamp}.json"
        json_path.write_text(json.dumps({
            "summary": summary,
            "agent_scores": scores,
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        md_path = out_path / f"evolution-{timestamp}.md"
        md_path.write_text(markdown, encoding="utf-8")

        print(f"✅ 进化报告已写入:")
        print(f"   JSON: {json_path}")
        print(f"   Markdown: {md_path}")
    else:
        print(markdown)

    return summary


def _build_evolution_report(summary, scores):
    """构建 Markdown 进化报告。"""
    lines = [
        "# 🧬 Agent 自进化评估报告",
        "",
        f"> 📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 回溯周期: {summary['lookback_days']} 天",
        "",
        "## Agent 评分排行",
        "",
        "| Agent | 综合分 | 等级 | 成功率 | 效率 | 质量 | 可靠性 |",
        "|---|---|---|---|---|---|---|",
    ]

    for agent_id, data in sorted(scores.items(), key=lambda x: x[1]["composite_score"], reverse=True):
        dims = data["dimensions"]
        grade_emoji = {"excellent": "🏆", "good": "✅", "needs_improvement": "⚠️", "critical": "🔴"}.get(data["grade"], "❓")
        lines.append(
            f"| {agent_id} | {data['composite_score']} | {grade_emoji} {data['grade']} "
            f"| {dims['success_rate']} | {dims['efficiency']} | {dims['quality']} | {dims['reliability']} |"
        )

    lines.append("")

    if summary["agents_needing_attention"]:
        lines.append("## ⚠️ 需要关注的 Agent")
        lines.append("")
        for agent_info in summary["agents_needing_attention"]:
            rec = agent_info.get("top_recommendation", {})
            lines.append(f"### {agent_info['agent_id']} (分数: {agent_info['score']})")
            if rec:
                lines.append(f"- **{rec.get('area', '')}**: {rec.get('detail', '')}")
            lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

def build_cli_parser():
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="Agent 自进化优化引擎 — 基于历史任务数据评估 Agent 表现并生成优化建议",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db-path", required=True, help="task_center.db 路径")
    parser.add_argument("--output-dir", default=None, help="报告输出目录")
    parser.add_argument("--lookback-days", type=int, default=30, help="回溯天数（默认 30）")
    parser.add_argument("--dry-run", action="store_true", help="只输出不写文件")
    parser.add_argument("--task-id", default=None, help="任务 ID（cron 集成）")
    return parser


def main():
    """CLI 主入口。"""
    configure_process_utf8_stdio()
    parser = build_cli_parser()
    args = parser.parse_args()

    run_evolution(
        db_path=args.db_path,
        output_dir=args.output_dir,
        lookback_days=args.lookback_days,
        dry_run=args.dry_run,
        task_id=args.task_id,
    )


if __name__ == "__main__":
    main()

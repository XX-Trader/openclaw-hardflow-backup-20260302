"""报告生成器"""

from datetime import datetime
from typing import List, Dict, Any
try:
    from ..analyzer.exception_stats import ExceptionStats
    from ..rules.base import DedupResult
except ImportError:
    from analyzer.exception_stats import ExceptionStats
    from rules.base import DedupResult


class ReportGenerator:
    """统计报告生成器"""

    def generate(
        self,
        input_file: str,
        output_file: str,
        dedup_results: List[DedupResult],
        exception_stats: ExceptionStats,
        original_lines: int,
        final_lines: int
    ) -> str:
        """
        生成统计报告

        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            dedup_results: 去重结果列表
            exception_stats: 异常统计结果
            original_lines: 原始行数
            final_lines: 最终行数

        Returns:
            报告内容
        """
        lines = []
        lines.append("=" * 40)
        lines.append("     日志去重统计报告")
        lines.append("=" * 40)
        lines.append("")

        # 基本信息
        lines.append(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"输入文件: {input_file}")
        lines.append(f"输出文件: {output_file}")
        lines.append("")

        # 去重统计
        lines.append("━" * 40)
        lines.append("  去重统计")
        lines.append("━" * 40)
        lines.append("")
        lines.append(f"原始行数:     {original_lines:,}")
        lines.append(f"去重后行数:   {final_lines:,}")
        compression_rate = ((original_lines - final_lines) / original_lines * 100) if original_lines > 0 else 0
        lines.append(f"压缩率:       {compression_rate:.1f}%")
        lines.append("")

        # 应用的规则
        if dedup_results:
            lines.append("应用的规则:")
            for result in dedup_results:
                lines.append(f"  ✓ {result.rule_name} (减少 {result.removed_count:,} 行)")
            lines.append("")

        # 异常统计
        lines.append("━" * 40)
        lines.append("  异常日志统计")
        lines.append("━" * 40)
        lines.append("")
        lines.append(f"异常日志总数: {exception_stats.total_count:,}")
        lines.append("")

        # 按级别分类
        if exception_stats.by_level:
            lines.append("按级别分类:")
            for level, count in sorted(exception_stats.by_level.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {level:>10}: {count:,} 条")
            lines.append("")

        # 按关键词分类
        if exception_stats.by_keyword:
            lines.append("按关键词分类:")
            for keyword, count in sorted(exception_stats.by_keyword.items(), key=lambda x: x[1], reverse=True):
                lines.append(f'  "{keyword}": {count:,} 条')
            lines.append("")

        # 高频异常
        if exception_stats.top_exceptions:
            lines.append("━" * 40)
            lines.append("  高频异常 (Top 10)")
            lines.append("━" * 40)
            lines.append("")

            for idx, exc in enumerate(exception_stats.top_exceptions, 1):
                lines.append(f"{idx}. {exc['line'][:80]} ({exc['count']} 次)")

                # 时间分布
                if exc['time_distribution']:
                    lines.append("   时间分布:")
                    for time_slot, count in list(exc['time_distribution'].items())[:3]:
                        lines.append(f"   - {time_slot}: {count} 次")
                lines.append("")

        # 时间分布总览
        if exception_stats.time_distribution:
            lines.append("━" * 40)
            lines.append("  时间分布总览")
            lines.append("━" * 40)
            lines.append("")

            for time_slot, count in exception_stats.time_distribution.items():
                lines.append(f"{time_slot}: {count} 条异常")
            lines.append("")

        lines.append("=" * 40)

        return "\n".join(lines)

    def save(self, content: str, file_path: str):
        """保存报告到文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

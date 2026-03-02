#!/usr/bin/env python3
"""
日志去重器 - 主程序

支持两种使用方式：
1. 独立命令行工具: python log_deduplicator.py <log_file>
2. Claude Code Skill: 通过 /log 命令调用
"""

import argparse
import sys
import os
from pathlib import Path
from typing import List, Optional

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ConfigManager, Config
from rules import DEFAULT_RULES, BaseRule
from analyzer import ExceptionAnalyzer, ExceptionStats
from reporter import ReportGenerator
from analyzer.order_failure_analyzer import OrderFailureAnalyzer, OrderFailureStats
from analyzer.business_logic_analyzer import BusinessLogicAnalyzer, BusinessLogicStats


class LogDeduplicator:
    """日志去重器主类"""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """
        初始化日志去重器

        Args:
            config_manager: 配置管理器，默认为 None（自动创建）
        """
        self.config_manager = config_manager or ConfigManager()
        self.config: Optional[Config] = None
        self.rules: List[BaseRule] = []
        self.reporter = ReportGenerator()

    def load_config(self) -> Config:
        """加载配置"""
        self.config = self.config_manager.load()
        return self.config

    def apply_rules(self, lines: List[str], rules: Optional[List[BaseRule]] = None) -> tuple[List[str], List]:
        """
        应用去重规则（使用标记保护重要日志）

        Args:
            lines: 原始日志行
            rules: 要应用的规则列表，默认使用 DEFAULT_RULES

        Returns:
            (去重后的行列表, 去重结果列表)
        """
        if rules is None:
            rules = DEFAULT_RULES

        # 标记重要日志并添加保护标记
        try:
            from rules.important_logs import ImportantLogsRule
        except ImportError:
            from .rules.important_logs import ImportantLogsRule
        important_rule = ImportantLogsRule(enabled=True)

        # 给重要日志添加特殊标记（在行尾）
        marked_lines = []
        important_map = {}  # {标记后的行: 原始行}

        for line in lines:
            if important_rule.is_important(line):
                marked_line = line + ' [IMPORTANT]'
                important_map[marked_line] = line
                marked_lines.append(marked_line)
            else:
                marked_lines.append(line)

        # 应用去重规则
        current_lines = marked_lines
        results = []

        for rule in rules:
            if not rule.enabled:
                continue

            result = rule.apply(current_lines)
            results.append(result)
            current_lines, _ = rule._process(current_lines)

        # 移除保护标记
        final_lines = []
        for line in current_lines:
            if line.endswith(' [IMPORTANT]'):
                # 重要日志，移除标记并恢复原始行
                original_line = important_map.get(line, line)
                final_lines.append(original_line.replace(' [IMPORTANT]', ''))
            else:
                final_lines.append(line)

        return final_lines, results

    def analyze_exceptions(self, lines: List[str]) -> ExceptionStats:
        """
        分析异常日志

        Args:
            lines: 日志行列表

        Returns:
            ExceptionStats: 异常统计结果
        """
        if not self.config:
            self.load_config()

        analyzer = ExceptionAnalyzer(self.config.exceptions)
        return analyzer.analyze(lines)

    def analyze_order_failures(self, lines: List[str]) -> OrderFailureStats:
        """
        分析下单失败日志

        Args:
            lines: 日志行列表

        Returns:
            OrderFailureStats: 下单失败统计结果
        """
        analyzer = OrderFailureAnalyzer()
        return analyzer.analyze(lines)

    def analyze_business_logic(self, lines: List[str], config_path: Optional[str] = None) -> BusinessLogicStats:
        """
        分析业务逻辑问题

        Args:
            lines: 日志行列表
            config_path: 业务逻辑配置文件路径

        Returns:
            BusinessLogicStats: 业务逻辑分析结果
        """
        analyzer = BusinessLogicAnalyzer(config_path=config_path)
        return analyzer.analyze(lines)

    def process_file(
        self,
        input_file: str,
        output_file: Optional[str] = None,
        preview_lines: int = 5,
        dry_run: bool = False,
        business_logic_config: Optional[str] = None
    ) -> dict:
        """
        处理日志文件

        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径，默认为 {input_file}-deduped.log
            preview_lines: 预览样本数量
            dry_run: 是否为预览模式（不实际写入文件）
            business_logic_config: 业务逻辑分析配置文件路径

        Returns:
            处理结果字典
        """
        # 加载配置
        self.load_config()

        # 读取输入文件
        input_path = Path(input_file)
        if not input_path.exists():
            raise FileNotFoundError(f"文件不存在: {input_file}")

        with open(input_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 移除行尾换行符（处理时保留）
        lines = [line.rstrip('\n') for line in lines]

        original_lines = len(lines)

        # 应用去重规则
        deduped_lines, dedup_results = self.apply_rules(lines)
        final_lines = len(deduped_lines)

        # 分析异常
        exception_stats = self.analyze_exceptions(lines)

        # 分析下单失败
        order_failure_stats = self.analyze_order_failures(lines)

        # 分析业务逻辑
        business_logic_stats = self.analyze_business_logic(lines, config_path=business_logic_config)

        # 确定输出文件路径
        if output_file is None:
            suffix = self.config.output.get("deduped_suffix", "-deduped")
            output_file = str(input_path) + suffix + input_path.suffix

        # 生成报告
        report_content = self.reporter.generate(
            input_file=str(input_path),
            output_file=output_file,
            dedup_results=dedup_results,
            exception_stats=exception_stats,
            original_lines=original_lines,
            final_lines=final_lines
        )

        # 生成下单失败报告
        order_failure_report = OrderFailureAnalyzer().generate_report(order_failure_stats)

        # 生成业务逻辑报告
        business_logic_report = BusinessLogicAnalyzer().generate_report(business_logic_stats)

        # 预览重复组
        preview = self._generate_preview(dedup_results, preview_lines)

        result = {
            "input_file": str(input_path),
            "output_file": output_file,
            "report_file": str(Path(output_file).parent / self.config.output.get("report_name", "report.txt")),
            "order_failure_report_file": str(Path(output_file).parent / "order_failure_report.txt"),
            "business_logic_report_file": str(Path(output_file).parent / "business_logic_report.txt"),
            "original_lines": original_lines,
            "final_lines": final_lines,
            "compression_rate": ((original_lines - final_lines) / original_lines * 100) if original_lines > 0 else 0,
            "dedup_results": dedup_results,
            "exception_stats": exception_stats,
            "order_failure_stats": order_failure_stats,
            "business_logic_stats": business_logic_stats,
            "preview": preview,
            "report": report_content,
            "order_failure_report": order_failure_report,
            "business_logic_report": business_logic_report,
            "dry_run": dry_run
        }

        # 如果不是预览模式，写入文件
        if not dry_run:
            # 写入去重后的日志
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(deduped_lines))

            # 写入报告
            report_file = Path(output_file).parent / self.config.output.get("report_name", "report.txt")
            self.reporter.save(report_content, str(report_file))

            # 写入下单失败报告
            order_failure_file = Path(output_file).parent / "order_failure_report.txt"
            with open(order_failure_file, 'w', encoding='utf-8') as f:
                f.write(order_failure_report)

            # 写入业务逻辑报告
            business_logic_file = Path(output_file).parent / "business_logic_report.txt"
            with open(business_logic_file, 'w', encoding='utf-8') as f:
                f.write(business_logic_report)

        return result

    def _generate_preview(self, dedup_results: List, preview_lines: int) -> List[str]:
        """生成预览内容"""
        preview = []

        for result in dedup_results[:preview_lines]:
            for line_num, group_info in list(result.groups.items())[:preview_lines]:
                preview.append(f"  [第 {line_num} 行附近] 连续相同 ×{group_info['count']}")
                preview.append(f"  > {group_info['line'][:100]}")
                preview.append("")

        return preview


def print_result(result: dict, verbose: bool = True):
    """打印处理结果"""
    print(f"[FILE] 输入文件: {result['input_file']}")
    print(f"[STATS] 原始行数: {result['original_lines']:,} 行")
    print("")
    print("━" * 50)
    print("  去重结果")
    print("━" * 50)
    print(f"去重后行数: {result['final_lines']:,} 行")
    print(f"压缩率: {result['compression_rate']:.1f}%")
    print("")

    # 打印应用的规则
    if result['dedup_results']:
        print("应用的规则:")
        for r in result['dedup_results']:
            print(f"  [OK] {r.rule_name} (减少 {r.removed_count:,} 行)")
    print("")

    # 打印异常统计
    stats = result['exception_stats']
    print(f"异常日志总数: {stats.total_count:,}")
    if stats.by_level:
        print("按级别分类:")
        for level, count in sorted(stats.by_level.items(), key=lambda x: x[1], reverse=True):
            print(f"  {level}: {count:,} 条")
    print("")

    # 打印下单失败统计
    order_stats = result.get('order_failure_stats')
    if order_stats:
        print(f"下单跳过总数: {order_stats.total_skipped:,}")
        if order_stats.skip_by_reason:
            print("跳过原因 Top 5:")
            sorted_reasons = sorted(
                order_stats.skip_by_reason.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            for reason, count in sorted_reasons:
                print(f"  {count:,} × {reason}")
        print("")

    # 打印业务逻辑问题
    logic_stats = result.get('business_logic_stats')
    if logic_stats:
        total_issues = len(logic_stats.issues)
        if total_issues > 0:
            print(f"业务逻辑问题: {total_issues}")
            if logic_stats.by_severity['critical'] > 0:
                print(f"  [CRITICAL] 严重: {logic_stats.by_severity['critical']}")
            if logic_stats.by_severity['high'] > 0:
                print(f"  [HIGH] 高: {logic_stats.by_severity['high']}")
            if logic_stats.by_severity['medium'] > 0:
                print(f"  [MEDIUM] 中: {logic_stats.by_severity['medium']}")
            if logic_stats.by_severity['low'] > 0:
                print(f"  [LOW] 低: {logic_stats.by_severity['low']}")
            
            # 显示流程完成率
            if logic_stats.flow_stats:
                starts = logic_stats.flow_stats.get('开始处理', 0)
                completes = logic_stats.flow_stats.get('交易完成', 0)
                if starts > 0:
                    rate = (completes / starts * 100) if starts > 0 else 0
                    print(f"  流程完成率: {completes}/{starts} ({rate:.1f}%)")
            print("")

    # 打印预览
    if result['preview'] and verbose:
        print("━" * 50)
        print("  去重预览")
        print("━" * 50)
        for line in result['preview']:
            print(line)
    print("")

    if not result['dry_run']:
        print(f"[OK] 输出文件: {result['output_file']}")
        print(f"[OK] 报告文件: {result['report_file']}")
        print(f"[OK] 下单失败报告: {result['order_failure_report_file']}")
        print(f"[OK] 业务逻辑报告: {result['business_logic_report_file']}")
    else:
        print("[INFO] 预览模式，未实际写入文件")


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='日志去重器 - 压缩大日志文件，生成异常统计报告',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python log_deduplicator.py app.log
  python log_deduplicator.py app.log -o result.log
  python log_deduplicator.py app.log --preview 10
  python log_deduplicator.py app.log --dry-run
  python log_deduplicator.py app.log --business-config config/trading_bot.json
        """
    )

    parser.add_argument('input_file', help='输入日志文件路径')
    parser.add_argument('-o', '--output', help='输出文件路径（默认: {输入文件}-deduped.log）')
    parser.add_argument('--preview', type=int, default=5, help='预览样本数量（默认: 5）')
    parser.add_argument('--dry-run', action='store_true', help='预览模式，不实际写入文件')
    parser.add_argument('--config', help='指定配置文件路径')
    parser.add_argument('--business-config', help='业务逻辑分析配置文件路径（JSON格式）')

    args = parser.parse_args()

    # 创建去重器
    config_manager = ConfigManager(args.config) if args.config else ConfigManager()
    deduplicator = LogDeduplicator(config_manager)

    try:
        # 处理文件
        result = deduplicator.process_file(
            input_file=args.input_file,
            output_file=args.output,
            preview_lines=args.preview,
            dry_run=args.dry_run,
            business_logic_config=getattr(args, 'business_config', None)
        )

        # 打印结果
        print_result(result)

    except Exception as e:
        print(f"[ERROR] 处理失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

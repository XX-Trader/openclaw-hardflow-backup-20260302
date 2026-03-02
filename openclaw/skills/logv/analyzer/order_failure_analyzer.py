"""下单失败分析器"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple
from collections import defaultdict, Counter


@dataclass
class OrderFailureStats:
    """下单失败统计结果"""
    total_skipped: int = 0
    total_executed: int = 0
    skip_by_reason: Dict[str, int] = field(default_factory=dict)
    skip_by_trader: Dict[str, int] = field(default_factory=dict)
    monitor_skip_stats: Dict[str, Tuple[int, int]] = field(default_factory=dict)  # (total, skipped)
    config_errors: List[Dict[str, Any]] = field(default_factory=list)
    threshold_issues: List[Dict[str, Any]] = field(default_factory=list)


class OrderFailureAnalyzer:
    """下单失败分析器"""

    # 监控跳过模式: 总计: X, 跳过: Y
    MONITOR_SKIP_PATTERN = re.compile(r'总计:\s*(\d+),\s*跳过:\s*(\d+)')

    # 交易员地址模式
    TRADER_ADDR_PATTERN = re.compile(r'0x[a-f0-9]{4,}')

    # 跳过原因模式
    SKIP_REASONS = [
        (r'交易员本次下单金额[\d.]+\s*USDC\s*<\s*交易员余额[\d.]+\s*USDC\s*的\s*[\d.]+\s*%阈值', '订单金额低于阈值'),
        (r'跟单金额[\d.]+\s*低于最小限制\s*[\d.]+\s*USDC', '低于最小订单限制'),
        (r'交易员余额为0，无法计算比例', '交易员余额为0'),
        (r'该方向持仓已达上限', '持仓达上限'),
        (r'不满足最小下单金额', '不满足最小下单金额'),
        (r'未在记录中找到跟随交易员', '未找到跟随记录'),
        (r'特殊策略限制', '特殊策略限制'),
        (r'订单参数无效', '订单参数无效'),
    ]

    # 配置错误模式
    CONFIG_ERRORS = [
        (r"标签 'copy_ratio' 配置格式错误", 'copy_ratio配置错误'),
        (r'内存持仓缓存为空', '持仓缓存为空'),
        (r'溢价计算出错', '溢价计算错误'),
        (r'API请求失败，状态码:\s*(\d+)', 'API请求失败'),
    ]

    def __init__(self):
        """初始化下单失败分析器"""
        # 编译跳过原因正则
        self.skip_patterns = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in self.SKIP_REASONS
        ]

        # 编译配置错误正则
        self.config_patterns = [
            (re.compile(pattern, re.IGNORECASE), reason)
            for pattern, reason in self.CONFIG_ERRORS
        ]

    def analyze(self, lines: List[str]) -> OrderFailureStats:
        """
        分析日志中的下单失败

        Args:
            lines: 日志行列表

        Returns:
            OrderFailureStats: 下单失败统计结果
        """
        stats = OrderFailureStats()

        for line in lines:
            # 分析跳过原因
            self._analyze_skip_reason(line, stats)

            # 分析监控跳过统计
            self._analyze_monitor_skip(line, stats)

            # 分析配置错误
            self._analyze_config_error(line, stats)

            # 分析阈值问题
            self._analyze_threshold_issue(line, stats)

        return stats

    def _analyze_skip_reason(self, line: str, stats: OrderFailureStats):
        """分析跳过原因"""
        if '跳过' not in line:
            return

        matched = False
        for pattern, reason in self.skip_patterns:
            if pattern.search(line):
                stats.skip_by_reason[reason] = stats.skip_by_reason.get(reason, 0) + 1
                matched = True
                break

        # 如果没有匹配到已知原因，尝试提取交易员
        if not matched:
            trader = self._extract_trader(line)
            if trader:
                stats.skip_by_trader[trader] = stats.skip_by_trader.get(trader, 0) + 1

        # 统计总跳过次数
        if '跳过该订单' in line or '跳过下单' in line or '跳过跟单' in line:
            stats.total_skipped += 1

    def _analyze_monitor_skip(self, line: str, stats: OrderFailureStats):
        """分析监控跳过统计"""
        if '[MONITOR]' not in line or '发现' not in line:
            return

        match = self.MONITOR_SKIP_PATTERN.search(line)
        if match:
            total = int(match.group(1))
            skipped = int(match.group(2))

            # 提取交易员地址
            trader_match = self.TRADER_ADDR_PATTERN.search(line)
            if trader_match:
                trader = trader_match.group()
                stats.monitor_skip_stats[trader] = (total, skipped)

    def _analyze_config_error(self, line: str, stats: OrderFailureStats):
        """分析配置错误"""
        if '[WARNING]' not in line and '[ERROR]' not in line:
            return

        for pattern, reason in self.config_patterns:
            if pattern.search(line):
                # 提取交易员（如果有）
                trader = self._extract_trader(line)

                error_info = {
                    'line': line.strip(),
                    'reason': reason,
                    'trader': trader,
                }

                # 提取状态码（如果是API错误）
                if 'API请求失败' in reason:
                    status_match = re.search(r'状态码:\s*(\d+)', line)
                    if status_match:
                        error_info['status_code'] = status_match.group(1)

                stats.config_errors.append(error_info)
                break

    def _analyze_threshold_issue(self, line: str, stats: OrderFailureStats):
        """分析阈值问题"""
        if '交易员本次下单金额' not in line or '<' not in line:
            return

        # 提取金额信息
        amount_match = re.search(r'下单金额\s*([\d.]+)\s*USDC', line)
        balance_match = re.search(r'交易员余额\s*([\d.]+)\s*USDC', line)
        threshold_match = re.search(r'阈值\s*\(([\d.]+)\s*USDC\)', line)

        if amount_match and balance_match and threshold_match:
            stats.threshold_issues.append({
                'line': line.strip(),
                'order_amount': float(amount_match.group(1)),
                'balance': float(balance_match.group(1)),
                'threshold': float(threshold_match.group(1)),
                'trader': self._extract_trader(line),
            })

    def _extract_trader(self, line: str) -> str:
        """提取交易员地址"""
        match = self.TRADER_ADDR_PATTERN.search(line)
        return match.group() if match else None

    def generate_report(self, stats: OrderFailureStats) -> str:
        """生成失败报告"""
        lines = []
        lines.append("=" * 80)
        lines.append("        下单失败/跳过分析报告")
        lines.append("=" * 80)
        lines.append("")

        # 监控跳过统计
        if stats.monitor_skip_stats:
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("  监控跳过统计 (按交易员)")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            # 按跳过率排序
            sorted_traders = sorted(
                stats.monitor_skip_stats.items(),
                key=lambda x: x[1][1] / x[1][0] if x[1][0] > 0 else 0,
                reverse=True
            )

            for trader, (total, skipped) in sorted_traders[:10]:
                skip_rate = (skipped / total * 100) if total > 0 else 0
                lines.append(f"  {trader}: {skipped}/{total} ({skip_rate:.1f}%)")

            lines.append("")

        # 跳过原因统计
        if stats.skip_by_reason:
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("  跳过原因统计")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            sorted_reasons = sorted(
                stats.skip_by_reason.items(),
                key=lambda x: x[1],
                reverse=True
            )

            for reason, count in sorted_reasons:
                lines.append(f"  {count:4d} × {reason}")

            lines.append("")

        # 阈值问题分析
        if stats.threshold_issues:
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("  阈值问题分析")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            # 分析阈值分布
            thresholds = [issue['threshold'] for issue in stats.threshold_issues]
            if thresholds:
                min_threshold = min(thresholds)
                max_threshold = max(thresholds)
                avg_threshold = sum(thresholds) / len(thresholds)

                lines.append(f"  阈值范围: {min_threshold:.2f} - {max_threshold:.2f} USDC")
                lines.append(f"  平均阈值: {avg_threshold:.2f} USDC")
                lines.append(f"  问题数量: {len(stats.threshold_issues)} 次")
                lines.append("")

                # 订单金额分布
                order_amounts = [issue['order_amount'] for issue in stats.threshold_issues]
                if order_amounts:
                    lines.append("  订单金额分布:")
                    lines.append(f"    最小: {min(order_amounts):.2f} USDC")
                    lines.append(f"    最大: {max(order_amounts):.2f} USDC")
                    lines.append(f"    平均: {sum(order_amounts) / len(order_amounts):.2f} USDC")
                    lines.append("")

        # 配置错误统计
        if stats.config_errors:
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            lines.append("  配置错误统计")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            # 按错误类型分组
            error_by_type = defaultdict(int)
            for error in stats.config_errors:
                error_by_type[error['reason']] += 1

            for error_type, count in sorted(error_by_type.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {count:4d} × {error_type}")

            lines.append("")

        # 建议
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("  优化建议")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if stats.threshold_issues:
            # 计算建议阈值
            order_amounts = [issue['order_amount'] for issue in stats.threshold_issues]
            if order_amounts:
                p90_amount = sorted(order_amounts)[int(len(order_amounts) * 0.9)]
                lines.append(f"1. 建议调整 min_trade_ratio 阈值，使 P90 订单能通过")
                lines.append(f"   当前平均订单: {sum(order_amounts) / len(order_amounts):.2f} USDC")
                lines.append(f"   P90 订单金额: {p90_amount:.2f} USDC")

        if any('copy_ratio配置错误' in e['reason'] for e in stats.config_errors):
            lines.append("2. 修复 copy_ratio 配置格式（应为字典，而非 float）")

        if any('交易员余额为0' in r for r in stats.skip_by_reason.keys()):
            lines.append("3. 启动时过滤余额为0的交易员")

        if any('低于最小订单限制' in r for r in stats.skip_by_reason.keys()):
            lines.append("4. 考虑降低最小订单限制")

        lines.append("")
        lines.append("=" * 80)

        return "\n".join(lines)

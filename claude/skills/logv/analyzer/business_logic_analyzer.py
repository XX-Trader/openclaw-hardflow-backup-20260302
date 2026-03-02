"""通用业务逻辑分析器 - 检测逻辑bug和参数异常

这个分析器提供通用的日志分析能力，通过配置可以适配不同项目。
"""

import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from collections import defaultdict
from pathlib import Path


@dataclass
class BusinessLogicIssue:
    """业务逻辑问题"""
    issue_type: str  # 问题类型
    severity: str  # 严重程度: critical, high, medium, low
    description: str  # 问题描述
    evidence: List[str]  # 证据日志
    context: Dict[str, Any]  # 上下文信息
    suggestion: str  # 修复建议


@dataclass
class BusinessLogicStats:
    """业务逻辑分析结果"""
    issues: List[BusinessLogicIssue] = field(default_factory=list)

    # 流程统计
    flow_stats: Dict[str, int] = field(default_factory=dict)
    parameter_anomalies: List[Dict[str, Any]] = field(default_factory=list)
    data_inconsistencies: List[Dict[str, Any]] = field(default_factory=list)

    # 按严重程度分类
    by_severity: Dict[str, int] = field(default_factory=lambda: {
        'critical': 0, 'high': 0, 'medium': 0, 'low': 0
    })


class BusinessLogicAnalyzer:
    """
    通用业务逻辑分析器

    通过配置文件或参数传入项目特定的规则和模式，
    实现对任意项目的日志分析。
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化分析器

        Args:
            config_path: 项目特定配置文件路径（JSON格式）
        """
        self.config = self._load_config(config_path)

        # 编译正则模式
        self.flow_patterns = self._compile_patterns(self.config.get('flow_steps', []))
        self.consistency_patterns = self._compile_patterns(self.config.get('consistency_checks', []))
        self.param_patterns = self._compile_patterns(self.config.get('parameter_checks', []))

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            'flow_steps': [],  # 流程步骤定义
            'consistency_checks': [],  # 一致性检查
            'parameter_checks': [],  # 参数检查
            'flow_grouping': {  # 流程分组配置
                'start_pattern': '',  # 开始标记
                'end_pattern': '',  # 结束标记
                'id_pattern': '',  # ID提取模式
            }
        }

        if config_path and Path(config_path).exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)

        return default_config

    def _compile_patterns(self, patterns: List[Dict]) -> List[Dict]:
        """编译正则表达式模式"""
        compiled = []
        for pattern_def in patterns:
            compiled_pattern = {
                **pattern_def,
                'regex': re.compile(pattern_def['pattern'], re.IGNORECASE)
            }
            compiled.append(compiled_pattern)
        return compiled

    def analyze(self, lines: List[str]) -> BusinessLogicStats:
        """
        分析日志行

        Args:
            lines: 日志行列表

        Returns:
            BusinessLogicStats: 分析结果
        """
        stats = BusinessLogicStats()

        # 1. 分析全局一致性问题
        self._analyze_global_consistency(lines, stats)

        # 2. 分析流程统计
        self._analyze_flow_statistics(lines, stats)

        # 3. 如果有流程分组配置，按流程分析
        if self.config.get('flow_grouping', {}).get('start_pattern'):
            groups = self._group_logs_by_flow(lines)
            for group_id, group_logs in groups.items():
                self._analyze_flow_group(group_id, group_logs, stats)
                self._analyze_parameters(group_id, group_logs, stats)

        return stats

    def _group_logs_by_flow(self, lines: List[str]) -> Dict[str, List[str]]:
        """按流程分组日志"""
        grouping_config = self.config.get('flow_grouping', {})
        start_pattern = grouping_config.get('start_pattern', '')
        end_pattern = grouping_config.get('end_pattern', '')
        id_pattern = grouping_config.get('id_pattern', '')

        if not start_pattern or not id_pattern:
            return {}

        groups = defaultdict(list)
        current_id = None
        start_regex = re.compile(start_pattern, re.IGNORECASE)
        end_regex = re.compile(end_pattern, re.IGNORECASE)
        id_regex = re.compile(id_pattern, re.IGNORECASE)

        for line in lines:
            # 检测新流程开始
            id_match = id_regex.search(line)
            if id_match:
                current_id = id_match.group(1) if id_match.groups() else str(len(groups))

            # 检测流程结束
            if end_regex.search(line):
                if current_id:
                    groups[current_id].append(line)
                    current_id = None
            elif current_id:
                groups[current_id].append(line)

        return dict(groups)

    def _analyze_flow_group(self, group_id: str, group_logs: List[str], stats: BusinessLogicStats):
        """分析单个流程组"""
        if not group_logs:
            return

        # 检查流程完整性
        flow_steps_found = defaultdict(int)
        for log in group_logs:
            for step_def in self.flow_patterns:
                if step_def['regex'].search(log):
                    flow_steps_found[step_def['name']] += 1

        # 检查是否有开始但没有结束
        start_count = flow_steps_found.get('开始处理', 0)
        end_count = flow_steps_found.get('交易完成', 0)

        if start_count > 0 and end_count == 0:
            stats.issues.append(BusinessLogicIssue(
                issue_type='流程中断',
                severity='high',
                description=f'流程 {group_id}... 开始但未完成',
                evidence=group_logs[:3],
                context={'group_id': group_id, 'log_count': len(group_logs)},
                suggestion='检查是否存在异常导致流程中断，查看ERROR日志'
            ))
            stats.by_severity['high'] += 1

        # 检查必要步骤缺失
        required_steps = self.config.get('required_steps', [])
        for step in required_steps:
            if flow_steps_found.get(step, 0) == 0:
                stats.issues.append(BusinessLogicIssue(
                    issue_type='必要步骤缺失',
                    severity='medium',
                    description=f'流程 {group_id}... 缺少步骤: {step}',
                    evidence=group_logs[:2],
                    context={'group_id': group_id, 'missing_step': step},
                    suggestion=f'检查{step}相关逻辑是否正常执行'
                ))
                stats.by_severity['medium'] += 1

    def _analyze_parameters(self, group_id: str, group_logs: List[str], stats: BusinessLogicStats):
        """分析参数异常"""
        for log in group_logs:
            for param_def in self.param_patterns:
                match = param_def['regex'].search(log)
                if match:
                    # 检查条件
                    condition_func = param_def.get('condition')
                    if condition_func:
                        try:
                            if not condition_func(match):
                                continue
                        except:
                            continue

                    stats.parameter_anomalies.append({
                        'group_id': group_id,
                        'type': param_def['name'],
                        'severity': param_def['severity'],
                        'description': param_def['description'],
                        'log': log.strip()
                    })

                    # 如果是严重问题，添加到issues列表
                    if param_def['severity'] in ['critical', 'high']:
                        stats.issues.append(BusinessLogicIssue(
                            issue_type=param_def['name'],
                            severity=param_def['severity'],
                            description=f'流程 {group_id}: {param_def["description"]}',
                            evidence=[log.strip()],
                            context={'group_id': group_id, 'match': match.groups()},
                            suggestion=param_def['description']
                        ))
                        stats.by_severity[param_def['severity']] += 1

    def _analyze_global_consistency(self, lines: List[str], stats: BusinessLogicStats):
        """分析全局一致性问题"""
        issue_counts = defaultdict(int)

        for line in lines:
            for check in self.consistency_patterns:
                if check['regex'].search(line):
                    issue_counts[check['name']] += 1

                    # 只记录前几个样本
                    if issue_counts[check['name']] <= 3:
                        stats.issues.append(BusinessLogicIssue(
                            issue_type=check['name'],
                            severity=check['severity'],
                            description=check['description'],
                            evidence=[line.strip()],
                            context={'line': line.strip()},
                            suggestion=check['description']
                        ))
                        stats.by_severity[check['severity']] += 1

        # 统计高频问题
        for name, count in issue_counts.items():
            if count > 50:  # 高频问题
                stats.data_inconsistencies.append({
                    'name': name,
                    'count': count,
                    'severity': next(
                        c['severity'] for c in self.consistency_patterns
                        if c['name'] == name
                    )
                })

    def _analyze_flow_statistics(self, lines: List[str], stats: BusinessLogicStats):
        """分析整体流程统计"""
        for step_def in self.flow_patterns:
            count = sum(1 for line in lines if step_def['regex'].search(line))
            if count > 0:
                stats.flow_stats[step_def['name']] = count

    def generate_report(self, stats: BusinessLogicStats) -> str:
        """生成业务逻辑分析报告"""
        lines = []
        lines.append("=" * 80)
        lines.append("        业务逻辑分析报告")
        lines.append("=" * 80)
        lines.append("")

        # 按严重程度分组显示问题
        severity_order = ['critical', 'high', 'medium', 'low']
        severity_labels = {
            'critical': '[CRITICAL] 严重',
            'high': '[HIGH] 高',
            'medium': '[MEDIUM] 中',
            'low': '[LOW] 低'
        }

        has_issues = False
        for severity in severity_order:
            issues = [i for i in stats.issues if i.severity == severity]
            if issues:
                has_issues = True
                lines.append("")
                lines.append(f"  {severity_labels[severity]} 问题 ({len(issues)} 个)")
                lines.append("")
                lines.append("")

                for i, issue in enumerate(issues[:10], 1):
                    lines.append(f"{i}. [{issue.issue_type}] {issue.description}")
                    if issue.evidence:
                        lines.append(f"   证据: {issue.evidence[0][:80]}...")
                    if issue.suggestion:
                        lines.append(f"   建议: {issue.suggestion}")
                    lines.append("")

                if len(issues) > 10:
                    lines.append(f"   ... 还有 {len(issues) - 10} 个问题")
                    lines.append("")

        if not has_issues:
            lines.append("[OK] 未发现明显的业务逻辑问题")
            lines.append("")

        # 流程统计
        if stats.flow_stats:
            lines.append("")
            lines.append("  流程统计")
            lines.append("")
            lines.append("")

            for step_name, count in sorted(stats.flow_stats.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {step_name}: {count:,} 次")
            lines.append("")

        # 参数异常统计
        if stats.parameter_anomalies:
            lines.append("")
            lines.append("  参数异常统计")
            lines.append("")
            lines.append("")

            by_type = defaultdict(int)
            for anomaly in stats.parameter_anomalies:
                by_type[anomaly['type']] += 1

            for anomaly_type, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"  {count:4d} × {anomaly_type}")
            lines.append("")

        # 数据一致性问题
        if stats.data_inconsistencies:
            lines.append("")
            lines.append("  数据一致性问题")
            lines.append("")
            lines.append("")

            for issue in sorted(stats.data_inconsistencies, key=lambda x: x['count'], reverse=True):
                lines.append(f"  [{issue['severity'].upper()}] {issue['name']}: {issue['count']:,} 次")
            lines.append("")

        # 总结
        lines.append("")
        lines.append("  问题总结")
        lines.append("")
        lines.append("")

        total_issues = sum(stats.by_severity.values())
        lines.append(f"总问题数: {total_issues}")
        lines.append(f"  [CRITICAL] 严重: {stats.by_severity['critical']}")
        lines.append(f"  [HIGH] 高: {stats.by_severity['high']}")
        lines.append(f"  [MEDIUM] 中: {stats.by_severity['medium']}")
        lines.append(f"  [LOW] 低: {stats.by_severity['low']}")
        lines.append("")

        if stats.by_severity['critical'] > 0 or stats.by_severity['high'] > 0:
            lines.append("[WARNING]  检测到严重/高优先级问题，建议优先处理！")
        elif stats.by_severity['medium'] > 10:
            lines.append("[WARNING]  检测到较多中等问题，建议逐步优化")
        else:
            lines.append("[OK]  系统运行正常，问题较少")

        lines.append("")
        lines.append("=" * 80)

        return "\n".join(lines)

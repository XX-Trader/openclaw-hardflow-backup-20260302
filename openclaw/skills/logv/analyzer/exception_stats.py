"""异常统计分析器"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple
from collections import defaultdict, Counter


@dataclass
class ExceptionStats:
    """异常统计结果"""
    total_count: int = 0
    by_level: Dict[str, int] = field(default_factory=dict)
    by_keyword: Dict[str, int] = field(default_factory=dict)
    top_exceptions: List[Dict[str, Any]] = field(default_factory=list)
    time_distribution: Dict[str, int] = field(default_factory=dict)


class ExceptionAnalyzer:
    """异常日志分析器"""

    # 日志级别正则
    LEVEL_PATTERN = re.compile(r'\b(ERROR|WARN|WARNING|CRITICAL|FATAL|FATALERROR)\b', re.IGNORECASE)

    # 时间戳正则
    TIME_PATTERN = re.compile(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2}')

    def __init__(self, exceptions_config: Dict[str, Any]):
        """
        初始化异常分析器

        Args:
            exceptions_config: 异常配置，包含 log_levels, keywords 等
        """
        self.log_levels = [lvl.upper() for lvl in exceptions_config.get("log_levels", [])]
        self.keywords = exceptions_config.get("keywords", [])
        self.custom_patterns = exceptions_config.get("custom_patterns", [])

        # 编译关键词正则
        self.keyword_patterns = [
            re.compile(rf'\b{re.escape(kw)}\b', re.IGNORECASE)
            for kw in self.keywords
        ]

    def analyze(self, lines: List[str]) -> ExceptionStats:
        """
        分析日志中的异常

        Args:
            lines: 日志行列表

        Returns:
            ExceptionStats: 异常统计结果
        """
        stats = ExceptionStats()

        # 按内容分组（用于统计高频异常）
        exception_groups = defaultdict(lambda: {"count": 0, "times": [], "first_line": ""})

        for line in lines:
            if self._is_exception(line):
                stats.total_count += 1

                # 提取日志级别
                level = self._extract_level(line)
                if level:
                    stats.by_level[level] = stats.by_level.get(level, 0) + 1

                # 提取关键词
                for keyword, pattern in zip(self.keywords, self.keyword_patterns):
                    if pattern.search(line):
                        stats.by_keyword[keyword] = stats.by_keyword.get(keyword, 0) + 1

                # 提取时间戳
                time_str = self._extract_time(line)

                # 归组统计（去除时间戳和行号后作为分组key）
                group_key = self._normalize_line(line)
                exception_groups[group_key]["count"] += 1
                exception_groups[group_key]["first_line"] = line
                if time_str:
                    exception_groups[group_key]["times"].append(time_str)

        # 生成高频异常 Top 10
        sorted_groups = sorted(
            exception_groups.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )[:10]

        for group_key, info in sorted_groups:
            stats.top_exceptions.append({
                "line": info["first_line"],
                "count": info["count"],
                "time_distribution": self._group_times(info["times"])
            })

        # 生成时间分布总览（按15分钟分组）
        all_times = []
        for info in exception_groups.values():
            all_times.extend(info["times"])
        stats.time_distribution = self._group_times(all_times, interval_minutes=15)

        return stats

    def _is_exception(self, line: str) -> bool:
        """判断是否为异常日志"""
        if not line or not line.strip():
            return False

        # 检查日志级别
        if self.LEVEL_PATTERN.search(line):
            level = self.LEVEL_PATTERN.search(line).group().upper()
            if level in self.log_levels:
                return True

        # 检查关键词
        for pattern in self.keyword_patterns:
            if pattern.search(line):
                return True

        return False

    def _extract_level(self, line: str) -> str:
        """提取日志级别"""
        match = self.LEVEL_PATTERN.search(line)
        if match:
            return match.group().upper()
        return None

    def _extract_time(self, line: str) -> str:
        """提取时间戳"""
        match = self.TIME_PATTERN.search(line)
        if match:
            return match.group()
        return None

    def _normalize_line(self, line: str) -> str:
        """规范化日志行（用于分组）"""
        # 移除时间戳
        normalized = self.TIME_PATTERN.sub('[TIME]', line)
        # 移除行首的行号（如果有）
        normalized = re.sub(r'^\[\d+\]', '', normalized)
        return normalized.strip()

    def _group_times(self, times: List[str], interval_minutes: int = 15) -> Dict[str, int]:
        """按时间间隔分组"""
        if not times:
            return {}

        grouped = defaultdict(int)
        for time_str in times:
            # 提取小时和分钟
            match = re.search(r'(\d{2}):(\d{2})', time_str)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2))
                # 计算时间段
                slot = (minute // interval_minutes) * interval_minutes
                time_slot = f"{hour:02d}:{slot:02d}-{hour:02d}:{slot + interval_minutes:02d}"
                grouped[time_slot] += 1

        return dict(sorted(grouped.items()))

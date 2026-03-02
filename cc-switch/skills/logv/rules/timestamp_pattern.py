"""时间戳模式去重规则"""

import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from .base import BaseRule


class TimestampPatternRule(BaseRule):
    """时间戳模式去重规则 - 折叠内容相同但时间戳不同的日志"""

    # 常见的时间戳模式
    TIME_PATTERNS = [
        # HH:MM:SS 或 HH:MM:SS.mmm
        (r'^\d{2}:\d{2}:\d{2}(\.\d+)?', 0),
        # YYYY-MM-DD HH:MM:SS
        (r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(\.\d+)?', 0),
        # MM/DD/YYYY HH:MM:SS
        (r'^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}', 0),
        # 日志级别后的时间戳: [INFO] 2025-01-09 10:00:00
        (r'\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(\.\d+)?\]', 0),
        # Unix 时间戳 (10位)
        (r'\b\d{10}\b', 0),
        # 带毫秒的 Unix 时间戳 (13位)
        (r'\b\d{13}\b', 0),
    ]

    def __init__(self, enabled: bool = True, min_repeat: int = 2):
        super().__init__(
            name="时间戳模式去重",
            rule_id="rule_003",
            enabled=enabled
        )
        self.min_repeat = min_repeat

    def _process(self, lines: List[str]) -> tuple[List[str], Dict[int, Dict[str, Any]]]:
        """
        处理日志行，折叠内容相同但时间戳不同的日志
        重要日志（标记为 [IMPORTANT]）将被完全保留，不参与任何去重
        """
        if not lines:
            return [], {}

        # 按模板分组（跳过重要日志）
        template_groups = defaultdict(lambda: {"lines": [], "indices": [], "times": []})

        for idx, line in enumerate(lines):
            # 跳过重要日志
            if '[IMPORTANT]' in line:
                continue
            
            # 提取模板（移除时间戳）
            template, timestamp = self._extract_template_and_timestamp(line)

            if template:
                template_groups[template]["lines"].append(line)
                template_groups[template]["indices"].append(idx)
                template_groups[template]["times"].append((timestamp, idx))

        # 生成去重后的行
        result = []
        groups = {}
        processed_indices = set()

        # 按原始顺序处理
        for template, info in sorted(template_groups.items(), key=lambda x: x[1]["indices"][0]):
            count = len(info["lines"])

            if count >= self.min_repeat:
                # 需要折叠
                first_idx = info["indices"][0]
                groups[first_idx] = {
                    "count": count,
                    "line": info["lines"][0],
                    "start_time": info["times"][0][0] if info["times"] else None,
                    "end_time": info["times"][-1][0] if info["times"] else None
                }

                # 生成折叠后的行
                display_line = info['lines'][0]
                if info["times"][0][0] and info["times"][-1][0]:
                    folded_line = f"{display_line} [×{count}, from: {info['times'][0][0]}, to: {info['times'][-1][0]}]"
                else:
                    folded_line = f"{display_line} [×{count}]"
                result.append(folded_line)

                processed_indices.update(info["indices"])
            else:
                # 不折叠，保留原行
                for idx, line in zip(info["indices"], info["lines"]):
                    if idx not in processed_indices:
                        result.append(line)
                        processed_indices.add(idx)

        # 添加未处理的重要日志（保持 [IMPORTANT] 标记）
        for idx, line in enumerate(lines):
            if idx not in processed_indices:
                result.append(line)

        return result, groups

    def _extract_template_and_timestamp(self, line: str) -> Tuple[str, str]:
        """
        从日志行中提取模板（移除时间戳）和时间戳

        Args:
            line: 日志行

        Returns:
            (模板字符串, 时间戳字符串)
        """
        if not line or not line.strip():
            return line, None

        for pattern, _ in self.TIME_PATTERNS:
            match = re.search(pattern, line)
            if match:
                timestamp = match.group()
                # 移除时间戳得到模板
                template = re.sub(pattern, '[TIME]', line, count=1)
                return template, timestamp

        # 没有匹配到时间戳模式
        return line, None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = super().to_dict()
        data["params"] = {
            "min_repeat": self.min_repeat
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimestampPatternRule':
        """从字典创建实例"""
        params = data.get("params", {})
        return cls(
            enabled=data.get("enabled", True),
            min_repeat=params.get("min_repeat", 2)
        )

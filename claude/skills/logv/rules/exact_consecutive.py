"""连续相同行去重规则"""

import re
from typing import List, Dict, Any
from .base import BaseRule


class ExactConsecutiveRule(BaseRule):
    """连续相同行去重规则"""

    # 时间戳正则模式（用于提取时间）
    TIME_PATTERNS = [
        r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}',  # 2025-01-09 10:00:00
        r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}',   # 01/09/2025 10:00:00
        r'\d{2}:\d{2}:\d{2}',                        # 10:00:00
        r'\d{10}',                                    # Unix 时间戳
    ]

    def __init__(self, enabled: bool = True, min_repeat: int = 2):
        super().__init__(
            name="连续相同行去重",
            rule_id="rule_001",
            enabled=enabled
        )
        self.min_repeat = min_repeat

    def _process(self, lines: List[str]) -> tuple[List[str], Dict[int, Dict[str, Any]]]:
        """
        处理连续相同的行
        重要日志（标记为 [IMPORTANT]）将被完全保留，不参与任何去重
        """
        if not lines:
            return [], {}

        result = []
        groups = {}
        current_line_num = 0

        i = 0
        while i < len(lines):
            line = lines[i]
            
            # 跳过重要日志
            if '[IMPORTANT]' in line:
                # 重要日志：直接添加，保持 [IMPORTANT] 标记
                result.append(line)
                current_line_num += 1
                i += 1
                continue
            
            start_line_num = current_line_num

            # 计算连续相同行数（跳过重要日志）
            repeat_count = 1
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                # 跳过重要日志
                if '[IMPORTANT]' in next_line:
                    break
                # 比较内容（移除 [IMPORTANT] 标记进行比较）
                if next_line == line:
                    repeat_count += 1
                    j += 1
                else:
                    break

            # 提取时间信息（如果有）
            first_time = self._extract_time(line)
            last_time = first_time

            if repeat_count > self.min_repeat:
                # 记录重复组信息
                if j - 1 < len(lines):
                    last_time = self._extract_time(lines[j - 1])

                groups[start_line_num] = {
                    "count": repeat_count,
                    "line": line,
                    "start_time": first_time,
                    "end_time": last_time
                }

                # 添加折叠后的行
                if last_time and last_time != first_time:
                    folded_line = f"{line} [×{repeat_count}, from: {first_time}, to: {last_time}]"
                else:
                    folded_line = f"{line} [×{repeat_count}]"
                result.append(folded_line)
            else:
                # 保留原行
                for k in range(repeat_count):
                    if i + k < len(lines):
                        result.append(lines[i + k])

            current_line_num += repeat_count
            i = j

        return result, groups

    def _extract_time(self, line: str) -> str:
        """从日志行中提取时间戳"""
        for pattern in self.TIME_PATTERNS:
            match = re.search(pattern, line)
            if match:
                return match.group()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = super().to_dict()
        data["params"] = {
            "min_repeat": self.min_repeat
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExactConsecutiveRule':
        """从字典创建实例"""
        params = data.get("params", {})
        return cls(
            enabled=data.get("enabled", True),
            min_repeat=params.get("min_repeat", 2)
        )

"""空行压缩规则"""

from typing import List, Dict, Any
from .base import BaseRule


class EmptyLineRule(BaseRule):
    """空行压缩规则"""

    def __init__(self, enabled: bool = True, min_consecutive: int = 2):
        super().__init__(
            name="空行压缩",
            rule_id="rule_002",
            enabled=enabled
        )
        self.min_consecutive = min_consecutive

    def _process(self, lines: List[str]) -> tuple[List[str], Dict[int, Dict[str, Any]]]:
        """
        压缩连续空行为单个空行
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

            # 检查是否为空行
            if not line or line.strip() == "":
                # 计算连续空行数（跳过重要日志）
                empty_count = 1
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    # 跳过重要日志
                    if '[IMPORTANT]' in next_line:
                        break
                    if not next_line or next_line.strip() == "":
                        empty_count += 1
                        j += 1
                    else:
                        break

                # 只有超过最小连续数量才压缩
                if empty_count >= self.min_consecutive:
                    groups[start_line_num] = {
                        "count": empty_count,
                        "line": "(空行)",
                        "start_time": None,
                        "end_time": None
                    }
                    result.append("")  # 保留一个空行
                else:
                    # 保留所有空行
                    for k in range(empty_count):
                        result.append("")

                current_line_num += empty_count
                i = j
            else:
                result.append(line)
                current_line_num += 1
                i += 1

        return result, groups

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = super().to_dict()
        data["params"] = {
            "min_consecutive": self.min_consecutive
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmptyLineRule':
        """从字典创建实例"""
        params = data.get("params", {})
        return cls(
            enabled=data.get("enabled", True),
            min_consecutive=params.get("min_consecutive", 2)
        )

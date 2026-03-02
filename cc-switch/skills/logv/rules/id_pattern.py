"""ID/数字模式去重规则"""

import re
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from .base import BaseRule


class IdPatternRule(BaseRule):
    """ID/数字模式去重规则 - 折叠内容相同但 ID/数字不同的日志"""

    # 需要替换为变量的模式
    PATTERNS = [
        # 0x 开头的十六进制地址（Ethereum 地址、交易哈希等）
        (r'\b0x[a-fA-F0-9]{8,64}\b', '[ID]'),
        # 纯数字 ID（4 位以上）
        (r'\b\d{4,}\b', '[NUM]'),
        # UUID 格式
        (r'\b[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}\b', '[UUID]'),
        # 短哈希（如 0x4da1a9...）
        (r'\b0x[a-fA-F0-9]{4,8}\.\.\.', '[HASH]'),
    ]

    def __init__(self, enabled: bool = True, min_repeat: int = 3):
        super().__init__(
            name="ID/数字模式去重",
            rule_id="rule_004",
            enabled=enabled
        )
        self.min_repeat = min_repeat

    def _process(self, lines: List[str]) -> tuple[List[str], Dict[int, Dict[str, Any]]]:
        """
        处理日志行，折叠内容相同但 ID/数字不同的日志
        重要日志（标记为 [IMPORTANT]）将被完全保留，不参与任何去重
        """
        if not lines:
            return [], {}

        # 先移除时间戳（如果存在），再处理 ID 模式
        from .timestamp_pattern import TimestampPatternRule
        timestamp_rule = TimestampPatternRule(enabled=False)

        # 按模板分组（跳过重要日志）
        template_groups = defaultdict(lambda: {"lines": [], "indices": [], "timestamps": []})

        for idx, line in enumerate(lines):
            # 跳过重要日志
            if '[IMPORTANT]' in line:
                continue
            
            # 提取时间戳
            _, timestamp = timestamp_rule._extract_template_and_timestamp(line)

            # 提取模板（移除时间戳和 ID/数字）
            template = self._extract_template(line)

            if template:
                template_groups[template]["lines"].append(line)
                template_groups[template]["indices"].append(idx)
                if timestamp:
                    template_groups[template]["timestamps"].append(timestamp)

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

                # 获取时间范围
                timestamps = info["timestamps"]
                start_time = timestamps[0] if timestamps else None
                end_time = timestamps[-1] if timestamps else None

                groups[first_idx] = {
                    "count": count,
                    "line": info["lines"][0],
                    "start_time": start_time,
                    "end_time": end_time
                }

                # 生成折叠后的行
                display_line = info['lines'][0]
                if start_time and end_time and start_time != end_time:
                    folded_line = f"{display_line} [×{count}, from: {start_time}, to: {end_time}]"
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

    def _extract_template(self, line: str) -> str:
        """
        从日志行中提取模板（移除时间戳和 ID/数字）

        Args:
            line: 日志行

        Returns:
            模板字符串
        """
        if not line or not line.strip():
            return line

        # 先移除时间戳
        from .timestamp_pattern import TimestampPatternRule
        timestamp_rule = TimestampPatternRule(enabled=False)
        template, _ = timestamp_rule._extract_template_and_timestamp(line)

        # 然后移除 ID/数字模式
        for pattern, replacement in self.PATTERNS:
            template = re.sub(pattern, replacement, template)

        return template

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = super().to_dict()
        data["params"] = {
            "min_repeat": self.min_repeat
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IdPatternRule':
        """从字典创建实例"""
        params = data.get("params", {})
        return cls(
            enabled=data.get("enabled", True),
            min_repeat=params.get("min_repeat", 3)
        )

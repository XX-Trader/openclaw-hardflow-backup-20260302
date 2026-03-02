"""规则基类"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class DedupResult:
    """去重结果"""
    rule_name: str
    original_lines: int
    deduped_lines: int
    removed_count: int
    # 每个重复组的信息: {行号: {count, line, start_time, end_time}}
    groups: Dict[int, Dict[str, Any]] = field(default_factory=dict)

    @property
    def compression_rate(self) -> float:
        """压缩率"""
        if self.original_lines == 0:
            return 0.0
        return (self.removed_count / self.original_lines) * 100


class BaseRule:
    """去重规则基类"""

    def __init__(self, name: str, rule_id: str, enabled: bool = True):
        self.name = name
        self.rule_id = rule_id
        self.enabled = enabled

    def apply(self, lines: List[str]) -> DedupResult:
        """
        应用去重规则

        Args:
            lines: 日志行列表

        Returns:
            DedupResult: 去重结果
        """
        original_count = len(lines)
        deduped_lines, groups = self._process(lines)
        removed_count = original_count - len(deduped_lines)

        return DedupResult(
            rule_name=self.name,
            original_lines=original_count,
            deduped_lines=len(deduped_lines),
            removed_count=removed_count,
            groups=groups
        )

    def _process(self, lines: List[str]) -> tuple[List[str], Dict[int, Dict[str, Any]]]:
        """
        处理日志行，返回去重后的行和重复组信息

        Args:
            lines: 日志行列表

        Returns:
            (去重后的行列表, 重复组信息字典)
        """
        raise NotImplementedError("子类必须实现此方法")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于保存配置）"""
        return {
            "id": self.rule_id,
            "name": self.name,
            "enabled": self.enabled,
            "type": self.__class__.__name__
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseRule':
        """从字典创建实例（用于加载配置）"""
        raise NotImplementedError("子类必须实现此方法")

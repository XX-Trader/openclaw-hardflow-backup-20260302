"""日志去重规则模块"""

from .base import BaseRule, DedupResult
from .exact_consecutive import ExactConsecutiveRule
from .empty_line import EmptyLineRule
from .timestamp_pattern import TimestampPatternRule
from .id_pattern import IdPatternRule

__all__ = [
    'BaseRule',
    'DedupResult',
    'ExactConsecutiveRule',
    'EmptyLineRule',
    'TimestampPatternRule',
    'IdPatternRule',
]

# 默认启用的规则列表
DEFAULT_RULES = [
    ExactConsecutiveRule(),    # Most safe: exact match
    EmptyLineRule(),            # Safe: empty line compression
    TimestampPatternRule(),     # Medium: pattern matching
    IdPatternRule(),            # Advanced: ID/number pattern matching
]

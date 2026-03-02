"""重要日志保留规则"""

import re
from typing import List, Dict, Any
from .base import BaseRule


class ImportantLogsRule(BaseRule):
    """重要日志保留规则 - 标记不应该被去重的重要日志"""

    # 默认的重要日志模式（可以配置）
    DEFAULT_IMPORTANT_PATTERNS = [
        # 启动相关日志 - 所有启动相关的日志都应该保留
        r'\[START\]',
        r'\[STARTUP\]',
        r'\[INIT\]',
        r'\[RATE-LIMIT\]',
        r'启动',
        r'初始化',

        # 配置相关日志
        r'\[CONFIG\]',
        r'\[MONITOR\].*配置',
        r'\[TRADE\].*钱包',
        r'\[TRADE\].*地址',
        r'交易员数量',
        r'监控地址列表',
        r'目标交易员',
        r'API端点',
        r'RPC节点',

        # DEBUG 日志中的配置信息（启动阶段）
        r'\[DEBUG\].*wallet_address',
        r'\[DEBUG\].*private_key',
        r'\[DEBUG\].*local_wallet_address',
        r'\[DEBUG\].*proxy_wallet_address',
        r'\[DEBUG\].*server_config',
        r'\[DEBUG\].*应用前',
        r'\[DEBUG\].*应用后',

        # 重要状态变更
        r'交易服务已启动',
        r'监控服务已启动',
        r'API轮询监控',
        r'加密密钥',
        r'API凭证',
        r'代理钱包',
        r'私钥',
        r'敏感数据',

        # 交易配置摘要（启动时显示）
        r'跟单仓位调整比例',
        r'订单超时',
        r'信号有效期',

        # 错误和警告（始终保留）
        r'\[ERROR\]',
        r'\[WARNING\]',
        r'\[WARN\]',
        r'\[CRITICAL\]',
        r'\[FATAL\]',

        # 异常关键词
        r'exception',
        r'failed',
        r'timeout',
        r'错误',
        r'失败',
    ]

    def __init__(self, enabled: bool = True, patterns: List[str] = None):
        super().__init__(
            name="重要日志标记",
            rule_id="rule_005",
            enabled=enabled
        )
        # 编译正则模式
        self.patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in (patterns or self.DEFAULT_IMPORTANT_PATTERNS)
        ]

    def is_important(self, line: str) -> bool:
        """
        判断日志行是否为重要日志（不应该被去重）

        Args:
            line: 日志行

        Returns:
            True 如果是重要日志
        """
        if not line or not line.strip():
            return False

        for pattern in self.patterns:
            if pattern.search(line):
                return True
        return False

    def _process(self, lines: List[str]) -> tuple[List[str], Dict[int, Dict[str, Any]]]:
        """
        标记重要日志（不修改内容，只标记）

        Args:
            lines: 日志行列表

        Returns:
            (原始行列表, 重要日志索引字典)
        """
        important_indices = {}

        for idx, line in enumerate(lines):
            if self.is_important(line):
                important_indices[idx] = {
                    "line": line,
                    "reason": "important_log"
                }

        # 不修改任何行，只返回标记
        return lines, important_indices

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = super().to_dict()
        data["params"] = {
            "patterns_count": len(self.patterns)
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ImportantLogsRule':
        """从字典创建实例"""
        return cls(
            enabled=data.get("enabled", True),
            patterns=None  # 使用默认模式
        )
